
// static/js/script.js - Updated with dynamic API URL

// ============================================================
// API CONFIGURATION - FIXED FOR DEPLOYMENT
// ============================================================

// Get the base URL dynamically
const API_BASE_URL = (() => {
    // If we're in production (deployed), use the current origin
    if (window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1') {
        return '';  // Use relative URLs, will use the same domain
    }
    // Development mode - use localhost
    return 'http://localhost:5000';
})();

// Update socket connection for production
const SOCKET_URL = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1' 
    ? window.location.origin 
    : 'http://localhost:5000';

// Connect socket with the correct URL
const socket = io(SOCKET_URL);

// ============================================================
// API HELPER WITH DYNAMIC URL
// ============================================================

async function apiRequest(endpoint, method = 'GET', data = null) {
    const url = API_BASE_URL + endpoint;
    const options = { 
        method, 
        headers: { 'Content-Type': 'application/json' } 
    };
    if (data && (method === 'POST' || method === 'PUT')) {
        options.body = JSON.stringify(data);
    }
    
    try {
        const response = await fetch(url, options);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        return await response.json();
    } catch (error) {
        console.error('API Request failed:', error);
        showToast('Network error. Please check your connection.', 'error');
        throw error;
    }
}









// static/js/script.js - Complete JavaScript
const socket = io();

// ============================================================
// SOCKET EVENTS
// ============================================================

socket.on('account_info', function(data) {
    if (data.balance) {
        document.getElementById('balance').textContent = '$' + data.balance.toFixed(2);
        document.getElementById('equity').textContent = '$' + data.equity.toFixed(2);
    }
});

socket.on('positions_updated', function(data) {
    updateOpenTrades(data.positions);
});

socket.on('signal_update', function(data) {
    addSignal(data);
});

socket.on('performance_update', function(data) {
    updatePerformance(data);
});

socket.on('bot_status', function(data) {
    updateRobotUI(data.running);
});

socket.on('broker_status', function(data) {
    updateBrokerUI(data.connected, data.broker_type);
});

socket.on('trade_log', function(data) {
    updateTradeLogs(data.logs);
});

socket.on('log_message', function(data) {
    addLogMessage(data.message);
});

// ============================================================
// TOAST NOTIFICATIONS
// ============================================================

function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 5000);
}

// ============================================================
// LOGIN FUNCTIONS
// ============================================================

function openLoginModal() {
    document.getElementById('loginModal').classList.add('active');
    document.getElementById('loginError').textContent = '';
    document.getElementById('loginSuccess').textContent = '';
}

function closeLoginModal() {
    document.getElementById('loginModal').classList.remove('active');
}

async function handleLogin(event) {
    event.preventDefault();

    const username = document.getElementById('loginUsername').value;
    const password = document.getElementById('loginPassword').value;
    const server = document.getElementById('loginServer').value;
    const brokerType = document.getElementById('loginBrokerType').value;

    document.getElementById('loginError').textContent = '';
    document.getElementById('loginSuccess').textContent = '';

    try {
        const result = await apiRequest('/api/login', 'POST', {
            username: username,
            password: password,
            server: server,
            broker_type: brokerType
        });

        if (result.success) {
            document.getElementById('loginSuccess').textContent = '✅ ' + result.message;
            showToast('✅ Connected to ' + result.broker + '!', 'success');
            updateBrokerUI(true, result.broker);
            document.getElementById('userDisplay').textContent = '👤 ' + username;
            setTimeout(closeLoginModal, 1500);
        } else {
            document.getElementById('loginError').textContent = '❌ ' + result.error;
            showToast('❌ Login failed: ' + result.error, 'error');
        }
    } catch (error) {
        document.getElementById('loginError').textContent = '❌ Connection error';
        showToast('❌ Login error', 'error');
    }
}

async function logout() {
    try {
        const result = await apiRequest('/api/logout', 'POST');
        if (result.success) {
            showToast('Logged out', 'warning');
            updateBrokerUI(false);
            document.getElementById('userDisplay').textContent = '';
            document.getElementById('balance').textContent = '--';
            document.getElementById('equity').textContent = '--';
            document.getElementById('profit').textContent = '--';
            document.getElementById('winRate').textContent = '--';
            updateOpenTrades([]);
            updatePerformance({});
        }
    } catch (error) {
        showToast('Logout error', 'error');
    }
}

// ============================================================
// UI UPDATE FUNCTIONS
// ============================================================

function updateBrokerUI(connected, type) {
    const badge = document.getElementById('connectionBadge');
    if (connected) {
        badge.textContent = type + ' Connected';
        badge.className = 'badge connected';
        document.getElementById('navLoginBtn').innerHTML = '<i class="fas fa-user"></i> ' + (type || 'Connected');
    } else {
        badge.textContent = 'Disconnected';
        badge.className = 'badge';
        document.getElementById('navLoginBtn').innerHTML = '<i class="fas fa-user"></i> Login';
    }
}

function updateOpenTrades(positions) {
    const container = document.getElementById('openTrades');
    if (!positions || positions.length === 0) {
        container.innerHTML = '<p style="opacity:0.5; text-align:center;">No open trades</p>';
        return;
    }
    container.innerHTML = positions.map(p => `
        <div style="display:flex; justify-content:space-between; align-items:center; padding:8px 0; border-bottom:1px solid rgba(255,255,255,0.05); flex-wrap:wrap; gap:5px;">
            <span>${p.symbol} ${(p.type || '').toUpperCase()} ${p.volume}</span>
            <span style="color: ${p.profit >= 0 ? 'var(--success)' : 'var(--danger)'};">${p.profit >= 0 ? '+' : ''}$${(p.profit || 0).toFixed(2)}</span>
            <button onclick="closeTrade('${p.ticket || p._id}')" class="btn btn-danger btn-sm">Close</button>
        </div>
    `).join('');
}

function addSignal(signal) {
    const container = document.getElementById('signalsList');
    const reasons = signal.reasons ? signal.reasons.join(' • ') : '';
    const signalDiv = document.createElement('div');
    signalDiv.className = 'signal-item';
    signalDiv.innerHTML = `
        <span>${signal.symbol}</span>
        <span class="signal-type ${signal.type}">${(signal.type || 'HOLD').toUpperCase()}</span>
        <span class="signal-confidence">${(signal.confidence || 0).toFixed(0)}%</span>
        <span style="font-size:0.7rem; opacity:0.5; width:100%;">${reasons}</span>
    `;
    container.prepend(signalDiv);
    while (container.children.length > 10) container.removeChild(container.lastChild);
}

function updatePerformance(data) {
    if (!data) return;
    document.getElementById('perfTotalTrades').textContent = data.total_trades || 0;
    document.getElementById('perfWins').textContent = data.winning_trades || 0;
    document.getElementById('perfLosses').textContent = data.losing_trades || 0;
    document.getElementById('perfWinRate').textContent = (data.win_rate || 0).toFixed(1) + '%';
    document.getElementById('perfProfit').textContent = '$' + (data.total_profit || 0).toFixed(2);
    document.getElementById('winRate').textContent = (data.win_rate || 0).toFixed(1) + '%';
    const profit = data.total_profit || 0;
    document.getElementById('profit').textContent = (profit >= 0 ? '+' : '') + '$' + profit.toFixed(2);
}

function updateRobotUI(running) {
    const dot = document.getElementById('robotStatusDot');
    const text = document.getElementById('robotStatusText');
    const badge = document.getElementById('robotStatusBadge');
    const btn = document.getElementById('robotToggleBtn');
    if (running) {
        dot.className = 'status-dot active';
        text.textContent = 'Robot is running';
        badge.textContent = 'ON';
        badge.style.background = 'var(--success)';
        btn.innerHTML = '<i class="fas fa-stop"></i> Stop';
        btn.className = 'btn btn-danger';
    } else {
        dot.className = 'status-dot inactive';
        text.textContent = 'Robot is offline';
        badge.textContent = 'OFF';
        badge.style.background = 'var(--danger)';
        btn.innerHTML = '<i class="fas fa-play"></i> Start';
        btn.className = 'btn btn-success';
    }
}

function updateTradeLogs(logs) {
    const container = document.getElementById('tradeLogs');
    if (!logs || logs.length === 0) {
        container.innerHTML = '<p style="opacity:0.5; text-align:center;">No trades executed</p>';
        return;
    }
    container.innerHTML = logs.slice(-10).reverse().map(log => `
        <div class="log-entry">
            <span class="log-time">[${new Date(log.time).toLocaleTimeString()}]</span>
            <span class="log-message ${log.status === 'OPEN' ? 'success' : 'warning'}">
                ${log.type} ${log.symbol} ${log.volume} @ ${log.entry.toFixed(5)}
                ${log.status === 'CLOSED' ? ` Profit: $${(log.profit || 0).toFixed(2)}` : ''}
                ${log.reasons ? ' | ' + log.reasons.join(' • ') : ''}
            </span>
        </div>
    `).join('');
}

function addLogMessage(message) {
    // Logs are displayed in the trade log section
}

// ============================================================
// API FUNCTIONS
// ============================================================

async function apiRequest(endpoint, method = 'GET', data = null) {
    const options = { method, headers: { 'Content-Type': 'application/json' } };
    if (data && (method === 'POST' || method === 'PUT')) options.body = JSON.stringify(data);
    const response = await fetch(endpoint, options);
    return response.json();
}

// ============================================================
// TRADING FUNCTIONS
// ============================================================

function placeTrade(tradeType) {
    const symbol = document.getElementById('tradeSymbol').value;
    const volume = parseFloat(document.getElementById('tradeVolume').value) || 0.01;
    const stopLoss = parseFloat(document.getElementById('tradeStopLoss').value) || 0;
    const takeProfit = parseFloat(document.getElementById('tradeTakeProfit').value) || 0;

    console.log('Placing trade:', { symbol, tradeType, volume, stopLoss, takeProfit });

    apiRequest('/api/trading/trade', 'POST', {
        symbol: symbol,
        type: tradeType,
        volume: volume,
        stopLoss: stopLoss,
        takeProfit: takeProfit
    }).then(result => {
        if (result.success) {
            showToast('✅ ' + tradeType.toUpperCase() + ' trade placed!', 'success');
            document.getElementById('tradeForm').reset();
        } else {
            showToast('❌ Failed: ' + (result.error || 'Unknown'), 'error');
        }
    }).catch(error => {
        showToast('❌ Failed to place trade', 'error');
    });
}

async function closeTrade(tradeId) {
    if (!confirm('Close this trade?')) return;
    try {
        const result = await apiRequest(`/api/trading/close/${tradeId}`, 'POST');
        if (result.success) {
            showToast(`✅ Trade closed! Profit: $${(result.profit || 0).toFixed(2)}`, 'success');
        } else {
            showToast('❌ Failed to close trade: ' + (result.error || 'Unknown'), 'error');
        }
    } catch (error) {
        showToast('❌ Failed to close trade', 'error');
    }
}

async function generateSignal() {
    try {
        const result = await apiRequest('/api/signals/generate', 'POST');
        if (result.success) {
            showToast('✅ New signal generated!', 'success');
        } else {
            showToast('❌ Failed to generate signal', 'error');
        }
    } catch (error) {
        showToast('❌ Failed to generate signal', 'error');
    }
}

// ============================================================
// ROBOT FUNCTIONS
// ============================================================

document.getElementById('robotToggleBtn').addEventListener('click', async function() {
    const isActive = this.textContent.includes('Start');
    try {
        const result = await apiRequest('/api/robot/toggle', 'POST', { isActive: isActive });
        if (result.success) {
            showToast(`Robot ${isActive ? 'started' : 'stopped'}`, 'success');
            updateRobotUI(result.isActive);
        } else {
            showToast('❌ Failed: ' + (result.error || 'Unknown'), 'error');
        }
    } catch (error) {
        showToast('❌ Failed to toggle robot', 'error');
    }
});

// ============================================================
// CONTACT FORM
// ============================================================

document.getElementById('contactForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const data = {
        name: document.getElementById('contactName').value,
        email: document.getElementById('contactEmail').value,
        message: document.getElementById('contactMessage').value
    };
    try {
        const result = await apiRequest('/api/contact', 'POST', data);
        if (result.success) {
            showToast('✅ Message sent!', 'success');
            document.getElementById('contactForm').reset();
        } else {
            showToast('❌ Failed to send', 'error');
        }
    } catch (error) {
        showToast('❌ Failed to send', 'error');
    }
});

// ============================================================
// MOBILE MENU
// ============================================================

document.getElementById('mobileMenuBtn').addEventListener('click', function() {
    document.getElementById('navLinks').classList.toggle('active');
});

// ============================================================
// INITIALIZATION
// ============================================================

document.addEventListener('DOMContentLoaded', async () => {
    try {
        const status = await apiRequest('/api/status');
        if (status.account) {
            document.getElementById('balance').textContent = '$' + (status.account.balance || 10000).toFixed(2);
            document.getElementById('equity').textContent = '$' + (status.account.equity || 10000).toFixed(2);
        }
        if (status.positions) updateOpenTrades(status.positions);
        if (status.performance) updatePerformance(status.performance);
        if (status.running) updateRobotUI(true);
        if (status.broker_connected) {
            updateBrokerUI(true, status.broker_type);
            document.getElementById('userDisplay').textContent = '👤 ' + (status.current_user || 'User');
        }
        if (status.trade_logs) updateTradeLogs(status.trade_logs);
    } catch (error) {
        console.error('Init error:', error);
    }

    // Auto-refresh every 10 seconds
    setInterval(async () => {
        try {
            const status = await apiRequest('/api/status');
            if (status.account) {
                document.getElementById('balance').textContent = '$' + (status.account.balance || 10000).toFixed(2);
                document.getElementById('equity').textContent = '$' + (status.account.equity || 10000).toFixed(2);
            }
        } catch (error) {
            // Silent refresh
        }
    }, 10000);
});

console.log('Ultimate Forex Bot UI loaded!');
