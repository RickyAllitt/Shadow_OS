
class AudioManager {
    constructor() {
        this.sounds = {};
        this.enabled = true;
        this.volume = 0.5;

        // Preload standard assets (Using legacy 'sounds' directory where available)
        this.load('level_up', '/static/sounds/levelup.mp3');
        this.load('quest_complete', '/static/sounds/quest_complete.mp3');
        this.load('notification', '/static/sounds/popup.mp3');
        this.load('arise', '/static/sounds/arise.mp3');
        this.load('buy_item', '/static/sounds/buy_item.mp3');
        this.load('timer_alarm', '/static/sounds/timer_alarm.mp3');
        this.load('glitch_error', '/static/sounds/glitch_error.mp3');
    }

    load(name, path) {
        const audio = new Audio(path);
        audio.preload = 'auto';
        this.sounds[name] = audio;
    }

    play(name) {
        if (!this.enabled) return;

        const sound = this.sounds[name];
        if (sound) {
            sound.currentTime = 0;
            // Human hearing is logarithmic, so an exponential curve makes the linear slider feel correct
            const MASTER_VOLUME_CAP = 1.0; // 100%
            sound.volume = Math.pow(this.volume, 2) * MASTER_VOLUME_CAP;

            // Play and catch potential "user interaction required" errors silently
            const playPromise = sound.play();
            if (playPromise !== undefined) {
                playPromise.catch(error => {
                    console.log(`Audio playback failed for ${name}:`, error);
                });
            }
        } else {
            console.warn(`Sound '${name}' not found.`);
        }
    }

    prime(name) {
        if (!this.enabled) return;
        const sound = this.sounds[name];
        if (sound) {
            sound.volume = 0; // Silent prime
            sound.play().then(() => {
                sound.pause();
                sound.currentTime = 0;
            }).catch(e => console.log(`Audio Prime Blocked for ${name}`));
        }
    }

    toggle() {
        this.enabled = !this.enabled;
        return this.enabled;
    }

    setVolume(vol) {
        this.volume = parseFloat(vol);
        if (isNaN(this.volume)) this.volume = 0.5;
    }
}

// Global Instance
window.audioManager = new AudioManager();
