/*
 * SystemUI: one place for toasts, modals and the popup sequence.
 *
 *   SystemUI.toast(message, category, { duration })   // non-blocking notice
 *   SystemUI.openModal(idOrEl) / closeModal(idOrEl)   // any .modal-overlay / .modal
 *   SystemUI.enqueue(fn)                              // fn(done): show one blocking popup at a time
 *
 * Server flash messages are rendered as hidden `.flash-data` elements (layout.html) and
 * routed here on page load: level-up overlay -> system modal -> anything pages enqueue
 * (e.g. the ARISE prompt) -> toasts.
 *
 * All message text is inserted with textContent: messages can contain user-entered quest titles.
 */
(function () {
    const MODAL_SELECTOR = '.modal-overlay, .modal, #levelUpOverlay';
    const MAX_TOASTS = 4;
    const TOAST_DURATIONS = { error: 8000, warning: 7000 };
    const DEFAULT_TOAST_DURATION = 4500;
    const MODAL_CATEGORIES = ['system_popup', 'quest_complete', 'arise_trigger'];

    const isVisible = el => el && getComputedStyle(el).display !== 'none';
    const resolve = idOrEl => typeof idOrEl === 'string' ? document.getElementById(idOrEl) : idOrEl;
    const play = name => { if (window.audioManager) window.audioManager.play(name); };

    // ---------------- TOASTS ----------------
    function toastContainer() {
        let c = document.getElementById('toastContainer');
        if (!c) {
            c = document.createElement('div');
            c.id = 'toastContainer';
            c.className = 'flash-container';
            c.setAttribute('role', 'status');
            c.setAttribute('aria-live', 'polite');
            document.body.appendChild(c);
        }
        return c;
    }

    function dismissToast(el) {
        if (!el.isConnected || el.dataset.dismissing) return;
        el.dataset.dismissing = '1';
        el.classList.add('flash-leaving');
        setTimeout(() => el.remove(), 400);
    }

    // Toasts raised while a dialog is open wait for it (and any queued popups) to close,
    // otherwise they would expire unseen behind the dimmed backdrop.
    function whenUnblocked(cb) {
        if (!topOpenModal() && !busy) cb();
        else setTimeout(() => whenUnblocked(cb), 400);
    }

    function toast(message, category = 'info', opts = {}) {
        if (!opts._ready) {
            whenUnblocked(() => toast(message, category, { ...opts, _ready: true }));
            return;
        }
        const container = toastContainer();
        const el = document.createElement('div');
        el.className = `flash-msg ${category}`;

        const text = document.createElement('span');
        text.className = 'flash-text';
        text.textContent = message;

        const close = document.createElement('button');
        close.type = 'button';
        close.className = 'flash-close';
        close.setAttribute('aria-label', 'Dismiss');
        close.textContent = '✖';
        close.addEventListener('click', () => dismissToast(el));

        el.append(text, close);
        container.appendChild(el);

        // Keep the stack short (mobile especially): drop the oldest
        const live = [...container.querySelectorAll('.flash-msg:not(.flash-leaving)')];
        live.slice(0, Math.max(0, live.length - MAX_TOASTS)).forEach(dismissToast);

        // Auto-dismiss, paused while hovered/focused so it can be read
        let remaining = opts.duration || TOAST_DURATIONS[category] || DEFAULT_TOAST_DURATION;
        let started = Date.now();
        let timer = setTimeout(() => dismissToast(el), remaining);
        const pause = () => { clearTimeout(timer); remaining -= Date.now() - started; };
        const resume = () => { started = Date.now(); timer = setTimeout(() => dismissToast(el), Math.max(1000, remaining)); };
        el.addEventListener('mouseenter', pause);
        el.addEventListener('mouseleave', resume);

        if (opts.sound !== false) play('notification');
        return el;
    }

    // ---------------- MODALS ----------------
    let lastFocused = null;

    function focusFirst(modal) {
        const target = modal.querySelector('[autofocus], button:not([disabled]), [href], input:not([type=hidden]), select, textarea');
        if (target) target.focus({ preventScroll: true });
    }

    function openModal(idOrEl) {
        const modal = resolve(idOrEl);
        if (!modal) return;
        modal.style.display = 'flex';
    }

    function closeModal(idOrEl) {
        const modal = resolve(idOrEl);
        if (!modal) return;
        modal.style.display = 'none';
    }

    function topOpenModal() {
        const open = [...document.querySelectorAll(MODAL_SELECTOR)].filter(isVisible);
        // Highest z-index wins; ties go to the later element in the DOM
        return open.sort((a, b) => (parseInt(getComputedStyle(a).zIndex) || 0) - (parseInt(getComputedStyle(b).zIndex) || 0)).pop();
    }

    // Watch every modal: whichever code opens/closes it (inline onclick handlers included),
    // we get focus handling, ARIA and a `modal:closed` event for the popup queue.
    function watchModals() {
        const observer = new MutationObserver(records => {
            records.forEach(({ target }) => {
                const nowOpen = isVisible(target);
                const wasOpen = target.dataset.open === '1';
                if (nowOpen === wasOpen) return;
                target.dataset.open = nowOpen ? '1' : '0';
                if (nowOpen) {
                    lastFocused = document.activeElement;
                    focusFirst(target);
                } else {
                    target.dispatchEvent(new Event('modal:closed'));
                    if (!topOpenModal() && lastFocused && lastFocused.isConnected) lastFocused.focus({ preventScroll: true });
                }
            });
        });
        document.querySelectorAll(MODAL_SELECTOR).forEach(m => {
            m.setAttribute('role', 'dialog');
            m.setAttribute('aria-modal', 'true');
            m.dataset.open = isVisible(m) ? '1' : '0';
            observer.observe(m, { attributes: true, attributeFilter: ['style', 'class'] });
        });
    }

    document.addEventListener('keydown', e => {
        if (e.key !== 'Escape') return;
        const top = topOpenModal();
        if (top) { e.preventDefault(); closeModal(top); }
    });

    // Click on the dimmed backdrop (not the panel) closes the modal
    document.addEventListener('click', e => {
        const t = e.target;
        if (t.matches && t.matches(MODAL_SELECTOR) && isVisible(t)) closeModal(t);
    });

    // ---------------- POPUP QUEUE ----------------
    const queue = [];
    let busy = false;

    function next() {
        if (busy || queue.length === 0) return;
        busy = true;
        const fn = queue.shift();
        let finished = false;
        fn(() => {
            if (finished) return;
            finished = true;
            busy = false;
            next();
        });
    }

    function enqueue(fn) { queue.push(fn); next(); }

    // Shows a modal and resolves the queue step when it is closed (by any means)
    function enqueueModal(idOrEl, beforeShow) {
        enqueue(done => {
            const modal = resolve(idOrEl);
            if (!modal) return done();
            if (beforeShow) beforeShow(modal);
            modal.addEventListener('modal:closed', done, { once: true });
            openModal(modal);
        });
    }

    // ---------------- FLASH ROUTING ----------------
    function showLevelUp(levelFlash) {
        enqueue(done => {
            const overlay = document.getElementById('levelUpOverlay');
            if (!overlay) return done();
            const [level, gained, preview] = levelFlash.textContent.trim().split('|');
            const next = document.getElementById('levelUpNext');
            if (next) next.textContent = preview || '';
            const sub = document.getElementById('levelUpDetail');
            if (sub) {
                const n = parseInt(gained) || 1;
                const lvl = parseInt(level);
                sub.textContent = lvl ? `LV ${lvl - n} → LV ${lvl} · ALL STATS +${n}` : 'SYSTEM LIMITS INCREASED';
            }
            overlay.addEventListener('modal:closed', done, { once: true });
            openModal(overlay);
            play('level_up');
            if (window.confetti) window.confetti({ particleCount: 150, spread: 100, origin: { y: 0.5 } });
            setTimeout(() => closeModal(overlay), preview ? 5500 : 3500);
        });
    }

    function routeFlashes() {
        const flashes = [...document.querySelectorAll('.flash-data')];
        if (flashes.length === 0) return;
        const popupsOn = window.popupsEnabled !== false;
        const cat = f => f.dataset.category;

        // 1. Level up overlay (first: it is the headline event)
        const levelFlash = flashes.find(f => cat(f) === 'levelup');
        if (levelFlash) showLevelUp(levelFlash);

        // 2. Blocking error dialog
        const errorFlash = flashes.find(f => cat(f) === 'error_modal');
        if (errorFlash) {
            enqueueModal('warningModal', () => {
                document.getElementById('warningText').textContent = errorFlash.textContent.trim();
            });
        }

        // 3. System modal: messages in the order the server flashed them
        const modalFlashes = flashes.filter(f =>
            cat(f) === 'arise_trigger' || (popupsOn && MODAL_CATEGORIES.includes(cat(f))));
        if (modalFlashes.length > 0) {
            const isArise = modalFlashes.some(f => cat(f) === 'arise_trigger');
            enqueueModal('systemModal', () => {
                const textEl = document.getElementById('systemModalText');
                textEl.replaceChildren(...modalFlashes.map(f => {
                    const p = document.createElement('p');
                    p.className = `u-mb-10 system-line ${cat(f)}`;
                    p.textContent = f.textContent.trim();
                    return p;
                }));
                document.getElementById('systemModalTitle').textContent = isArise ? 'ARISE' : 'SYSTEM NOTIFICATION';
                if (isArise) {
                    play('arise');
                    if (window.confetti) window.confetti({ particleCount: 120, spread: 90, origin: { y: 0.6 }, colors: ['#9d4edd', '#5a189a', '#e0aaff'] });
                } else if (!levelFlash) {
                    play('notification');
                }
            });
        }

        // 4. Everything else is a toast (incl. system popups when the user turned popups off)
        const handled = new Set([levelFlash, errorFlash, ...modalFlashes]);
        flashes.filter(f => !handled.has(f)).forEach((f, i) =>
            toast(f.textContent.trim(), cat(f), { sound: i === 0 && handled.size === 0 }));
    }

    document.addEventListener('DOMContentLoaded', () => {
        watchModals();
        routeFlashes();
        // Timezone picker: options come from the browser (Intl), no server payload
        const tzSelect = document.getElementById('settingTimezone');
        if (tzSelect && Intl.supportedValuesOf) {
            const current = tzSelect.dataset.current;
            const zones = Intl.supportedValuesOf('timeZone');
            if (!zones.includes(current)) zones.unshift(current);
            tzSelect.replaceChildren(...zones.map(z => new Option(z.replace(/_/g, ' '), z, false, z === current)));
            const detected = Intl.DateTimeFormat().resolvedOptions().timeZone;
            const hint = document.getElementById('timezoneDetected');
            if (detected && detected !== current && hint) {
                hint.hidden = false;
                hint.textContent = `This device is in ${detected}. `;
                const use = document.createElement('button');
                use.type = 'button';
                use.className = 'btn-small';
                use.textContent = 'USE IT';
                use.addEventListener('click', () => { tzSelect.value = detected; hint.hidden = true; });
                hint.appendChild(use);
            }
        }
        // Registration: record the device timezone
        const regTz = document.getElementById('registerTimezone');
        if (regTz) regTz.value = Intl.DateTimeFormat().resolvedOptions().timeZone || '';

        // Countdowns: <span data-ends="ISO-8601 with offset"> -> "Ends in 3d 4h"
        const tick = () => document.querySelectorAll('[data-ends]').forEach(el => {
            const ms = new Date(el.dataset.ends) - new Date();
            if (isNaN(ms)) return;
            const d = Math.floor(ms / 864e5), h = Math.floor(ms % 864e5 / 36e5), m = Math.floor(ms % 36e5 / 6e4);
            el.textContent = ms <= 0 ? 'Week over' : 'Ends in ' + (d ? `${d}d ${h}h` : h ? `${h}h ${m}m` : `${m}m`);
        });
        tick();
        setInterval(tick, 60000);

        // Narrow screens: keep the current page's tab visible in the scrolling nav
        const active = document.querySelector('.app-nav-link.active');
        if (active) active.scrollIntoView({ block: 'nearest', inline: 'center' });
    });

    window.SystemUI = { toast, openModal, closeModal, enqueue, enqueueModal };
})();
