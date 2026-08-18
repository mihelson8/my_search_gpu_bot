// pages/index/index.js
const app = getApp();

Page({
  data: {
    queryText: "",
    isLoading: false,
    isRecording: false,
    result: null
  },

  onLoad() {
    this.recorderManager = wx.getRecorderManager();
    this.innerAudioContext = wx.createInnerAudioContext();

    // Voice record events
    this.recorderManager.onStart(() => {
      console.log("Recorder started");
    });

    this.recorderManager.onStop((res) => {
      console.log("Recorder stopped", res.tempFilePath);
      this.handleVoiceFile(res.tempFilePath);
    });

    this.recorderManager.onError((err) => {
      console.error("Recorder error", err);
      this.setData({ isRecording: false });
      wx.showToast({ title: "Ошибка записи", icon: "none" });
    });
  },

  onInput(e) {
    this.setData({ queryText: e.detail.value });
  },

  clearInput() {
    this.setData({ queryText: "", result: null });
  },

  selectQuickTag(e) {
    const text = e.currentTarget.dataset.text;
    this.setData({ queryText: text }, () => {
      this.doTranslate();
    });
  },

  doTranslate() {
    const q = this.data.queryText.trim();
    if (!q) {
      wx.showToast({ title: "Введите текст", icon: "none" });
      return;
    }

    this.setData({ isLoading: true });

    wx.request({
      url: `${app.globalData.baseUrl}/api/translate`,
      data: { q: q },
      method: "GET",
      timeout: 10000,
      success: (res) => {
        if (res.statusCode === 200 && res.data) {
          this.setData({ result: res.data });
        } else {
          wx.showToast({ title: "Ошибка перевода", icon: "none" });
        }
      },
      fail: (err) => {
        console.error("Translation request error:", err);
        wx.showToast({ title: "Сетевая ошибка", icon: "none" });
      },
      complete: () => {
        this.setData({ isLoading: false });
      }
    });
  },

  startVoiceRecord() {
    this.setData({ isRecording: true });
    wx.vibrateShort();
    this.recorderManager.start({
      duration: 30000,
      sampleRate: 16000,
      numberOfChannels: 1,
      encodeBitRate: 48000,
      format: "mp3"
    });
  },

  stopVoiceRecord() {
    if (this.data.isRecording) {
      this.setData({ isRecording: false });
      this.recorderManager.stop();
    }
  },

  handleVoiceFile(tempFilePath) {
    wx.showLoading({ title: "Распознавание..." });
    // In mini program we can upload the voice file to our backend server
    wx.uploadFile({
      url: `${app.globalData.baseUrl}/api/voice_translate`,
      filePath: tempFilePath,
      name: "voice",
      success: (res) => {
        wx.hideLoading();
        try {
          const data = JSON.parse(res.data);
          if (data && data.result) {
            this.setData({ queryText: data.query || "", result: data.result });
          }
        } catch (e) {
          // fallback query
        }
      },
      fail: (err) => {
        wx.hideLoading();
        // Fallback info
        wx.showToast({ title: "Голосовой ввод", icon: "none" });
      }
    });
  },

  playAudio(e) {
    const text = e.currentTarget.dataset.text;
    const lang = e.currentTarget.dataset.lang;
    if (!text) return;

    const audioUrl = `${app.globalData.baseUrl}/api/tts?text=${encodeURIComponent(text)}&lang=${lang}`;
    this.innerAudioContext.src = audioUrl;
    this.innerAudioContext.play();

    wx.showToast({ title: "🔊 Воспроизведение", icon: "none", duration: 1000 });
  },

  copyText(e) {
    const text = e.currentTarget.dataset.text;
    if (!text) return;

    wx.setClipboardData({
      data: text,
      success: () => {
        wx.showToast({ title: "Скопировано", icon: "success" });
      }
    });
  }
});
