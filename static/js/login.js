/* Both login forms submit normally when JavaScript is unavailable. */
(() => {
    const password = document.getElementById('password');
    const toggle = document.querySelector('.login-password-toggle');
    if (!password || !toggle) return;
    toggle.hidden = false;
    toggle.addEventListener('click', () => {
        const reveal = password.type === 'password';
        password.type = reveal ? 'text' : 'password';
        toggle.setAttribute('aria-pressed', String(reveal));
        toggle.setAttribute('aria-label', reveal ? 'Hide password' : 'Show password');
    });
})();
