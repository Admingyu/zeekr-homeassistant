/** Home Assistant card that starts and displays a Zeekr sentinel RTC session. */
class ZeekrSentinelCard extends HTMLElement {
  /** Initialize the card state and create its initial controls. */
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._engine = null;
    this._streamIndex = null;
    this._mediaType = null;
    this._rtcEvents = null;
    this._remoteUsers = new Set();
    this._activeRemoteUser = null;
    /** Track whether the active remote stream has rendered its first video frame. */
    this._videoFirstFrameSeen = false;
    /** Report a stalled remote video without restarting a verified RTC session. */
    this._videoWaitTimer = null;
    /** Track whether microphone audio is currently published to the vehicle room. */
    this._isTalking = false;
    /** Serialize microphone start/stop so room cleanup can wait for it safely. */
    this._talkOperation = null;
    this._renewTimer = null;
    this._selectedVin = "";
    this._vehiclesLoaded = false;
    this._render();
  }

  /** Store Lovelace configuration and request the available vehicle list. */
  setConfig(config = {}) {
    this._config = config;
    this._render();
    this._loadVehicles();
  }

  /** Attach the active Home Assistant connection and load vehicles. */
  set hass(hass) {
    this._hass = hass;
    this._loadVehicles();
  }

  /** Return the active Home Assistant connection. */
  get hass() {
    return this._hass;
  }

  /** Load the vehicle selector when the card enters the dashboard. */
  connectedCallback() {
    this._loadVehicles();
  }

  /** Leave the RTC room and destroy its engine when the card is removed. */
  disconnectedCallback() {
    this._leaveRoom();
  }

  /** Estimate the card height for Lovelace's layout engine. */
  getCardSize() {
    return 7;
  }

  /** Render card controls and connect their user actions. */
  _render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; }
        ha-card { padding: 16px; }
        .controls { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
        select, button { min-height: 40px; padding: 0 12px; }
        select { flex: 1; min-width: 220px; }
        /* The SDK wrapper uses height: 100%; min-height alone leaves it at zero. */
        #video { position: relative; height: 300px; margin-top: 12px; overflow: hidden; background: #111; }
        #video video { display: block; width: 100%; height: 100%; position: absolute; inset: 0; object-fit: contain; }
        #empty { color: #ddd; position: absolute; inset: 0; display: grid; place-items: center; }
        #empty[hidden] { display: none; }
        #status { margin-top: 8px; min-height: 1.5em; }
        #streams { margin-top: 8px; }
        .view-controls { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-top: 8px; }
        #talk { width: 100%; margin-top: 8px; background: var(--success-color, #0f7b4b); color: white; }
        #talk.active { background: var(--error-color, #b91c3c); }
      </style>
      <ha-card header="哨兵实时视频">
        <div class="controls">
          <select id="vehicle" aria-label="选择车辆" disabled>
            <option value="">正在读取车辆…</option>
          </select>
          <button id="start" disabled>开始观看</button>
          <button id="stop" disabled>停止</button>
        </div>
        <div id="status" role="status">等待 Home Assistant 连接</div>
        <div id="video"><div id="empty">未连接</div></div>
        <select id="streams" aria-label="远端视频源" hidden disabled></select>
        <div class="view-controls" aria-label="切换哨兵视角">
          <button type="button" data-direction="front" disabled>前</button>
          <button type="button" data-direction="back" disabled>后</button>
          <button type="button" data-direction="left" disabled>左</button>
          <button type="button" data-direction="right" disabled>右</button>
        </div>
        <button id="talk" type="button" disabled>开始远程喊话</button>
      </ha-card>`;
    this._vehicleSelect = this.shadowRoot.querySelector("#vehicle");
    this._startButton = this.shadowRoot.querySelector("#start");
    this._stopButton = this.shadowRoot.querySelector("#stop");
    this._status = this.shadowRoot.querySelector("#status");
    this._video = this.shadowRoot.querySelector("#video");
    this._empty = this.shadowRoot.querySelector("#empty");
    this._streamSelect = this.shadowRoot.querySelector("#streams");
    this._viewButtons = this.shadowRoot.querySelectorAll("[data-direction]");
    this._talkButton = this.shadowRoot.querySelector("#talk");
    this._startButton.addEventListener("click", () => this._startRoom());
    this._stopButton.addEventListener("click", () => this._leaveRoom());
    this._talkButton.addEventListener("click", () => this._toggleTalking());
    for (const button of this._viewButtons) {
      button.addEventListener("click", () => this._changeView(button));
    }
    this._vehicleSelect.addEventListener("change", () => {
      this._selectedVin = this._vehicleSelect.value;
      this._startButton.disabled = !this._selectedVin || Boolean(this._engine);
    });
    this._streamSelect.addEventListener("change", () => {
      this._selectRemoteUser(this._streamSelect.value);
    });
  }

  /** Load this account's supported VINs through the authenticated HA WebSocket. */
  async _loadVehicles() {
    if (!this._hass || !this._vehicleSelect || this._vehiclesLoaded) return;
    try {
      const response = await this._hass.callWS({ type: "zeekr/list_vehicles" });
      const vehicles = response.vehicles || [];
      this._vehicleSelect.replaceChildren();
      for (const vehicle of vehicles) {
        const option = document.createElement("option");
        option.value = vehicle.vin;
        option.textContent = vehicle.name;
        this._vehicleSelect.append(option);
      }
      this._selectedVin = vehicles[0]?.vin || "";
      this._vehicleSelect.value = this._selectedVin;
      this._vehicleSelect.disabled = vehicles.length === 0;
      this._startButton.disabled = vehicles.length === 0;
      this._status.textContent = vehicles.length ? "选择车辆后开始观看" : "没有可用车辆";
      this._vehiclesLoaded = true;
    } catch (error) {
      this._status.textContent = `读取车辆失败：${this._message(error)}`;
    }
  }

  /** Fetch a short-lived RTC session, join its room, and wait for vehicle video. */
  async _startRoom() {
    if (!this._hass || !this._selectedVin || this._engine) return;
    this._startButton.disabled = true;
    this._vehicleSelect.disabled = true;
    this._status.textContent = "正在获取直播会话…";
    try {
      const session = await this._hass.callWS({
        type: "zeekr/start_sentinel",
        vin: this._selectedVin,
      });
      const { default: VERTC, MediaType, StreamIndex } = await import(
        "https://unpkg.com/@volcengine/rtc@4.69.2/index.esm.min.js"
      );
      this._streamIndex = StreamIndex;
      this._mediaType = MediaType;
      this._rtcEvents = VERTC.events;
      this._remoteUsers.clear();
      this._activeRemoteUser = null;
      this._videoFirstFrameSeen = false;
      this._isTalking = false;
      this._engine = VERTC.createEngine(session.appId);
      const engine = this._engine;
      this._engine.on(this._rtcEvents.onUserPublishStream, (event) => {
        const isVideo = event.mediaType === this._mediaType.VIDEO ||
          event.mediaType === this._mediaType.AUDIO_AND_VIDEO;
        if (!isVideo) return;
        this._remoteUsers.add(event.userId);
        this._refreshStreamSelect();
        this._selectRemoteUser(event.userId);
      });
      this._engine.on(this._rtcEvents.onUserUnpublishStream, (event) => this._removeRemoteUser(event));
      this._engine.on(this._rtcEvents.onUserLeave, (event) => this._removeRemoteUser(event));
      this._engine.on(this._rtcEvents.onError, (error) => {
        this._status.textContent = `RTC 错误：${this._message(error)}`;
      });
      this._engine.on(this._rtcEvents.onRemoteVideoFirstFrame, ({ userId }) => {
        if (this._engine !== engine || userId !== this._activeRemoteUser) return;
        this._videoFirstFrameSeen = true;
        clearTimeout(this._videoWaitTimer);
        this._videoWaitTimer = null;
        this._empty.hidden = true;
        this._status.textContent = "正在播放车辆视频";
      });
      await this._engine.joinRoom(
        session.accessToken,
        session.roomId,
        { userId: session.userId },
        {
          isAutoPublish: false,
          isAutoSubscribeAudio: false,
          isAutoSubscribeVideo: true,
        },
      );
      if (!this._activeRemoteUser) {
        this._status.textContent = "已加入房间，等待车辆视频…";
        this._empty.hidden = false;
      }
      this._stopButton.disabled = false;
      this._talkButton.disabled = false;
      for (const button of this._viewButtons) button.disabled = false;
      this._startVideoWaitTimer();
      this._scheduleRenewal(session);
    } catch (error) {
      const message = this._message(error);
      await this._leaveRoom(true);
      this._status.textContent = `连接失败：${message}`;
    }
  }

  /** Bind a remote user's main stream and report binding failures in the card.
   * @returns {Promise<void>} Completes after the SDK finishes binding the player.
   */
  async _selectRemoteUser(userId) {
    const engine = this._engine;
    if (!engine || !this._remoteUsers.has(userId)) return;
    const index = this._streamIndex?.STREAM_INDEX_MAIN;
    if (index == null) return;
    const switchingUser = this._activeRemoteUser !== userId;
    try {
      if (this._activeRemoteUser && switchingUser) {
        await engine.setRemoteVideoPlayer(index, { userId: this._activeRemoteUser });
      }
      if (switchingUser) {
        this._activeRemoteUser = userId;
        this._videoFirstFrameSeen = false;
        this._empty.hidden = false;
        this._empty.textContent = "等待车辆视频…";
      }
      await engine.setRemoteVideoPlayer(index, { userId, renderDom: this._video });
    } catch (error) {
      if (this._engine === engine) {
        if (this._activeRemoteUser === userId) this._activeRemoteUser = null;
        this._empty.hidden = false;
        this._status.textContent = `播放器绑定失败：${this._message(error)}`;
      }
      return;
    }
    if (this._engine !== engine) return;
    if (!this._videoFirstFrameSeen) {
      this._status.textContent = "播放器已绑定，等待车辆视频首帧";
      this._startVideoWaitTimer();
    }
  }

  /** Report whether a joined room is waiting for publication or for its first frame. */
  _startVideoWaitTimer() {
    clearTimeout(this._videoWaitTimer);
    this._videoWaitTimer = setTimeout(() => {
      this._videoWaitTimer = null;
      if (!this._engine || this._videoFirstFrameSeen) return;
      this._status.textContent = this._activeRemoteUser
        ? "入房 20 秒仍无视频首帧，请检查 RTC 连接"
        : "入房 20 秒未收到车辆视频流";
    }, 20000);
  }

  /** Remove a remote publisher when its video ends or it leaves the room. */
  _removeRemoteUser(event) {
    if (event.mediaType === this._mediaType?.AUDIO) return;
    const userId = event.userId || event.userInfo?.userId;
    if (!userId) return;
    this._remoteUsers.delete(userId);
    if (this._activeRemoteUser === userId) {
      this._activeRemoteUser = null;
      this._videoFirstFrameSeen = false;
      this._video.querySelectorAll("video").forEach((video) => video.remove());
      this._empty.hidden = false;
      this._empty.textContent = "等待车辆视频…";
      this._status.textContent = "视频源已停止，等待车辆视频…";
      this._startVideoWaitTimer();
    }
    this._refreshStreamSelect();
  }

  /** Send the verified Zeekr room broadcast that selects one vehicle camera view. */
  async _changeView(button) {
    const engine = this._engine;
    if (!engine) return;
    for (const viewButton of this._viewButtons) viewButton.disabled = true;
    this._talkButton.disabled = true;
    const label = button.textContent.trim();
    try {
      const result = engine.sendRoomMessage(JSON.stringify({
        payload: { direction: button.dataset.direction },
        event: "cmd_action_change_source",
      }));
      if (!result) throw new Error("RTC 未返回房间消息发送结果");
      await result;
      if (this._engine === engine) this._status.textContent = `已请求切换到${label}视角`;
    } catch (error) {
      if (this._engine === engine) {
        this._status.textContent = `${label}视角切换失败：${this._message(error)}`;
      }
    } finally {
      for (const viewButton of this._viewButtons) {
        viewButton.disabled = this._engine !== engine;
      }
      this._talkButton.disabled = this._engine !== engine || Boolean(this._talkOperation);
    }
  }

  /** Stop publishing microphone audio and release the browser capture device. */
  async _stopTalking(engine) {
    try {
      await engine.unpublishStream(this._mediaType.AUDIO);
    } finally {
      try {
        await engine.stopAudioCapture();
      } finally {
        this._isTalking = false;
        this._talkButton.textContent = "开始远程喊话";
        this._talkButton.classList.remove("active");
      }
    }
  }

  /** Start or stop the verified on-demand RTC microphone publishing sequence. */
  async _toggleTalking() {
    const engine = this._engine;
    if (!engine || this._talkOperation) return;
    this._talkButton.disabled = true;
    this._stopButton.disabled = true;
    for (const button of this._viewButtons) button.disabled = true;

    const operation = (async () => {
      if (this._isTalking) {
        await this._stopTalking(engine);
        this._status.textContent = "远程喊话已停止";
        return;
      }
      // Microphone capture is unavailable on LAN HTTP origins. Check before
      // entering the SDK so the user sees the required access method.
      if (!window.isSecureContext) {
        throw new Error("当前为非安全页面，请通过 HTTPS（受信任证书）或 localhost 访问 Home Assistant 后使用麦克风");
      }
      if (typeof navigator.mediaDevices?.getUserMedia !== "function") {
        throw new Error("当前浏览器未提供麦克风采集接口，请使用支持麦克风采集的浏览器");
      }
      await engine.startAudioCapture();
      try {
        await engine.publishStream(this._mediaType.AUDIO);
      } catch (error) {
        try {
          await engine.stopAudioCapture();
        } catch (cleanupError) {
          throw new Error(
            `${this._message(error)}；麦克风清理失败：${this._message(cleanupError)}`,
          );
        }
        throw error;
      }
      this._isTalking = true;
      this._talkButton.textContent = "停止远程喊话";
      this._talkButton.classList.add("active");
      this._status.textContent = "远程喊话中";
    })();
    this._talkOperation = operation;

    try {
      await operation;
    } catch (error) {
      if (this._engine === engine) {
        this._status.textContent = `远程喊话失败：${this._message(error)}`;
      }
    } finally {
      if (this._talkOperation === operation) this._talkOperation = null;
      this._talkButton.disabled = this._engine !== engine;
      this._stopButton.disabled = this._engine !== engine;
      for (const button of this._viewButtons) button.disabled = this._engine !== engine;
    }
  }

  /** Rebuild the optional selector when multiple remote video publishers exist. */
  _refreshStreamSelect() {
    this._streamSelect.replaceChildren();
    for (const userId of this._remoteUsers) {
      const option = document.createElement("option");
      option.value = userId;
      option.textContent = userId;
      this._streamSelect.append(option);
    }
    this._streamSelect.hidden = this._remoteUsers.size < 2;
    this._streamSelect.disabled = this._remoteUsers.size < 2;
    if (this._activeRemoteUser) this._streamSelect.value = this._activeRemoteUser;
  }

  /** Schedule a fresh room session just before the current session expires. */
  _scheduleRenewal(session) {
    clearTimeout(this._renewTimer);
    const limits = [];
    const expiry = this._expiryTime(session.expireAt);
    if (expiry) limits.push(expiry);
    const duration = Number(session.liveDuration);
    if (Number.isFinite(duration) && duration > 0) {
      const durationMs = duration > 86400 ? duration : duration * 1000;
      limits.push(Date.now() + durationMs);
    }
    if (!limits.length) return;
    const renewIn = Math.max(1000, Math.min(...limits) - Date.now() - 5000);
    this._renewTimer = setTimeout(async () => {
      const vin = this._selectedVin;
      await this._leaveRoom(false);
      this._selectedVin = vin;
      this._vehicleSelect.value = vin;
      await this._startRoom();
    }, renewIn);
  }

  /** Parse an absolute numeric or ISO expiry without exposing RTC credentials. */
  _expiryTime(value) {
    if (value == null || value === "") return null;
    const numeric = Number(value);
    if (Number.isFinite(numeric) && numeric > 0) {
      if (numeric > 1000000000000) return numeric;
      if (numeric > 1000000000) return numeric * 1000;
      return null;
    }
    const parsed = Date.parse(value);
    return Number.isFinite(parsed) ? parsed : null;
  }

  /** Leave the active room, clear video, and optionally restore card controls. */
  async _leaveRoom(restoreControls = true) {
    clearTimeout(this._renewTimer);
    this._renewTimer = null;
    clearTimeout(this._videoWaitTimer);
    this._videoWaitTimer = null;
    this._talkButton.disabled = true;
    this._stopButton.disabled = true;
    for (const button of this._viewButtons) button.disabled = true;
    if (this._talkOperation) {
      try {
        await this._talkOperation;
      } catch (_) {
        // The talk operation already reports its error; room cleanup still continues.
      }
    }
    const engine = this._engine;
    if (engine && this._isTalking) {
      try {
        await this._stopTalking(engine);
      } catch (_) {
        // A failed audio stop must not prevent leaving and destroying the RTC engine.
      }
    }
    this._engine = null;
    this._activeRemoteUser = null;
    this._videoFirstFrameSeen = false;
    this._remoteUsers.clear();
    this._refreshStreamSelect();
    if (engine) {
      try {
        await engine.leaveRoom();
      } catch (_) {
        // RTC may already have closed the room; still destroy the local engine below.
      } finally {
        engine.destroy();
      }
    }
    this._video.querySelectorAll("video").forEach((video) => video.remove());
    this._empty.hidden = false;
    this._empty.textContent = "未连接";
    if (restoreControls) {
      this._status.textContent = "未连接";
      this._vehicleSelect.disabled = false;
      this._startButton.disabled = !this._selectedVin;
    }
  }

  /** Convert an RTC/UI exception to short status text, excluding token fields. */
  _message(error) {
    return error?.message ? String(error.message).slice(0, 160) : "未知错误";
  }
}

/** Register the card type with Home Assistant's custom card picker. */
customElements.define("zeekr-sentinel-card", ZeekrSentinelCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "zeekr-sentinel-card",
  name: "Zeekr 哨兵视频",
  description: "选择车辆并播放哨兵 RTC 视频流",
  preview: false,
});
