// JWT 토큰 관리
function getToken() {
    return localStorage.getItem('access_token');
}

function setToken(accessToken, refreshToken) {
    localStorage.setItem('access_token', accessToken);
    if (refreshToken) {
        localStorage.setItem('refresh_token', refreshToken);
    }
}

function clearToken() {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
}

function logout() {
    clearToken();
    document.cookie = 'access_token=; Path=/; Expires=Thu, 01 Jan 1970 00:00:00 GMT';
    window.location.href = '/login';
}

// Preview panel
document.addEventListener('htmx:afterSwap', function(event) {
    if (event.detail.target.id === 'preview-panel') {
        event.detail.target.style.display = 'block';
    }
});
