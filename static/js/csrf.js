(function () {
    'use strict';

    const meta = document.querySelector('meta[name="csrf-token"]');
    const token = meta ? meta.getAttribute('content') : '';
    if (!token) return;

    const unsafeMethods = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

    function isSameOrigin(rawUrl) {
        try {
            return new URL(rawUrl, window.location.href).origin === window.location.origin;
        } catch (_) {
            return false;
        }
    }

    const originalFetch = window.fetch.bind(window);
    window.fetch = function (input, init) {
        const options = Object.assign({}, init || {});
        const request = input instanceof Request ? input : null;
        const method = String(options.method || (request && request.method) || 'GET').toUpperCase();
        const rawUrl = request ? request.url : input;

        if (unsafeMethods.has(method) && isSameOrigin(rawUrl)) {
            const headers = new Headers(options.headers || (request && request.headers) || undefined);
            if (!headers.has('X-CSRFToken')) {
                headers.set('X-CSRFToken', token);
            }
            options.headers = headers;
        }
        return originalFetch(input, options);
    };

    document.addEventListener('submit', function (event) {
        const form = event.target;
        if (!(form instanceof HTMLFormElement)) return;
        const method = String(form.method || 'GET').toUpperCase();
        if (!unsafeMethods.has(method) || !isSameOrigin(form.action || window.location.href)) return;
        if (form.querySelector('input[name="csrf_token"]')) return;

        const field = document.createElement('input');
        field.type = 'hidden';
        field.name = 'csrf_token';
        field.value = token;
        form.appendChild(field);
    }, true);
})();
