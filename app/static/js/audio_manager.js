
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
            sound.volume = this.volume;

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

    toggle() {
        this.enabled = !this.enabled;
        return this.enabled;
    }
}

// Global Instance
window.audioManager = new AudioManager();
