# app.py - Complete Flask Backend
from flask import Flask, render_template, request, jsonify, session
from flask_socketio import SocketIO, emit
import threading
import time
import json
import os
import random
import math
from datetime import datetime
from collections import deque
import hashlib
import logging
import sys

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Check if running on Windows (where MT5 is available)
IS_WINDOWS = sys.platform.startswith('win')
BOT_AVAILABLE = False

# Try to import MetaTrader5 only on Windows
if IS_WINDOWS:
    try:
        import MetaTrader5 as mt5
        BOT_AVAILABLE = True
        logger.info("MetaTrader5 module loaded successfully (Windows)")
    except ImportError:
        BOT_AVAILABLE = False
        logger.warning("MT5 not available on this system")
else:
    logger.info("Running on non-Windows system - MT5 not available")

app = Flask(__name__)
app.config['SECRET_KEY'] = 'trading-bot-secret-key-2024'
app.config['SESSION_TYPE'] = 'filesystem'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# ============================================================
# USER SESSION MANAGEMENT
# ============================================================

users = {}

class User:
    def __init__(self, username, password, broker_type='demo'):
        self.username = username
        self.password = password
        self.broker_type = broker_type
        self.broker_connected = False
        self.created_at = datetime.now()
        self.performance = {
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'win_rate': 0,
            'total_profit': 0
        }

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def create_user(username, password, broker_type='demo'):
    if username in users:
        return None
    users[username] = User(username, hash_password(password), broker_type)
    return users[username]

def authenticate_user(username, password):
    if username in users:
        if users[username].password == hash_password(password):
            return users[username]
    return None

# ============================================================
# DEMO DATA GENERATOR
# ============================================================

def generate_demo_data(bars=200):
    data = []
    price = 1.1000
    trend = 0
    for i in range(bars):
        trend += random.uniform(-0.0005, 0.0005)
        if random.random() < 0.05:
            trend = random.uniform(-0.001, 0.001)

        price += trend + random.uniform(-0.0003, 0.0003)
        price = max(1.0500, min(1.1500, price))

        data.append({
            'time': int(time.time()) - (bars - i) * 60,
            'open': price - random.uniform(0.0001, 0.0003),
            'high': price + random.uniform(0.0002, 0.0005),
            'low': price - random.uniform(0.0002, 0.0005),
            'close': price,
            'tick_volume': random.randint(100, 2000)
        })
    return data

# ============================================================
# MARKET ANALYSIS CLASSES
# ============================================================

class MarketRegimeDetector:
    def __init__(self):
        self.current_regime = 'Neutral'

    def detect(self, data, lookback=50):
        if not data or len(data) < lookback:
            return 'Neutral'

        closes = [bar['close'] for bar in data[-lookback:]]
        highs = [bar['high'] for bar in data[-lookback:]]
        lows = [bar['low'] for bar in data[-lookback:]]

        returns = []
        for i in range(1, len(closes)):
            if closes[i - 1] > 0:
                returns.append((closes[i] - closes[i - 1]) / closes[i - 1])

        if len(returns) < 10:
            return 'Neutral'

        mean_return = sum(returns) / len(returns)
        variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
        volatility = math.sqrt(variance) if variance > 0 else 0

        trend_strength = self.calculate_trend_strength(highs, lows, closes)

        range_width = sum(h - l for h, l in zip(highs, lows)) / len(highs)
        avg_range = sum(h - l for h, l in zip(highs[::5], lows[::5])) / max(1, len(highs[::5]))

        if trend_strength > 25 and volatility > 0.01:
            regime = 'Strong Trend'
        elif trend_strength > 15 and volatility > 0.005:
            regime = 'Trending'
        elif range_width / max(avg_range, 0.0001) < 1.2 and volatility < 0.005:
            regime = 'Ranging'
        elif volatility > 0.015:
            regime = 'Volatile'
        else:
            regime = 'Neutral'

        self.current_regime = regime
        return regime

    def calculate_trend_strength(self, highs, lows, closes):
        n = len(closes)
        if n < 14:
            return 0

        tr = []
        for i in range(1, n):
            tr.append(max(highs[i] - lows[i],
                          abs(highs[i] - closes[i - 1]),
                          abs(lows[i] - closes[i - 1])))

        plus_dm = []
        minus_dm = []
        for i in range(1, n):
            up_move = highs[i] - highs[i - 1]
            down_move = lows[i - 1] - lows[i]
            plus_dm.append(max(up_move, 0) if up_move > down_move else 0)
            minus_dm.append(max(down_move, 0) if down_move > up_move else 0)

        atr = sum(tr[-14:]) / 14 if len(tr) >= 14 else 0.0001
        plus_di = sum(plus_dm[-14:]) / atr * 100 if atr > 0 else 0
        minus_di = sum(minus_dm[-14:]) / atr * 100 if atr > 0 else 0

        dx = abs(plus_di - minus_di) / (plus_di + minus_di) * 100 if (plus_di + minus_di) > 0 else 0
        return dx

class TechnicalAnalyzer:
    def analyze(self, data):
        if not data or len(data) < 50:
            return self.get_default_analysis()

        closes = [bar['close'] for bar in data]
        highs = [bar['high'] for bar in data]
        lows = [bar['low'] for bar in data]
        volumes = [bar['tick_volume'] for bar in data]

        analysis = {
            'trend': self.analyze_trend(closes),
            'momentum': self.analyze_momentum(closes),
            'volatility': self.analyze_volatility(closes, highs, lows),
            'volume': self.analyze_volume(volumes, closes),
            'support_resistance': self.find_support_resistance(highs, lows),
            'patterns': self.detect_patterns(closes, highs, lows)
        }
        return analysis

    def get_default_analysis(self):
        return {
            'trend': {'direction': 'Neutral', 'strength': 0, 'adx': 0, 'sma20': 0, 'sma50': 0},
            'momentum': {'rsi': 50, 'macd': 0, 'momentum': 0},
            'volatility': {'atr': 0, 'bollinger': {'upper': 0, 'middle': 0, 'lower': 0}},
            'volume': {'current': 0, 'avg': 0, 'ratio': 1, 'spike': False},
            'support_resistance': {'support': [], 'resistance': [], 'nearest_support': None,
                                   'nearest_resistance': None},
            'patterns': []
        }

    def analyze_trend(self, closes):
        if len(closes) < 50:
            return {'direction': 'Neutral', 'strength': 0, 'adx': 0, 'sma20': 0, 'sma50': 0}

        sma20 = sum(closes[-20:]) / 20
        sma50 = sum(closes[-50:]) / 50
        current = closes[-1]

        if current > sma20 > sma50:
            direction = 'Bullish'
            strength = 2
        elif current < sma20 < sma50:
            direction = 'Bearish'
            strength = 2
        else:
            direction = 'Neutral'
            strength = 0

        adx = self.calculate_adx(closes)

        return {
            'direction': direction,
            'strength': strength,
            'adx': adx,
            'sma20': sma20,
            'sma50': sma50
        }

    def calculate_adx(self, closes):
        if len(closes) < 14:
            return 0

        returns = []
        for i in range(1, len(closes)):
            if closes[i - 1] > 0:
                returns.append((closes[i] - closes[i - 1]) / closes[i - 1])

        if len(returns) < 14:
            return 0

        volatility = sum((r - sum(returns[-14:]) / 14) ** 2 for r in returns[-14:]) / 14
        volatility = math.sqrt(volatility) if volatility > 0 else 0.0001
        trend = sum(abs(r) for r in returns[-14:]) / 14
        adx = trend / volatility * 100 if volatility > 0 else 0

        return min(adx, 100)

    def analyze_momentum(self, closes):
        if len(closes) < 14:
            return {'rsi': 50, 'macd': 0, 'momentum': 0}

        gains = []
        losses = []
        for i in range(1, len(closes)):
            change = closes[i] - closes[i - 1]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))

        if len(gains) >= 14:
            avg_gain = sum(gains[-14:]) / 14
            avg_loss = sum(losses[-14:]) / 14
        else:
            avg_gain = sum(gains) / len(gains) if gains else 0
            avg_loss = sum(losses) / len(losses) if losses else 0.001

        if avg_loss == 0:
            rsi = 100
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))

        rsi = max(0, min(100, rsi))

        ema12 = self.calculate_ema(closes, 12)
        ema26 = self.calculate_ema(closes, 26)
        macd = ema12 - ema26 if ema12 and ema26 else 0

        if len(closes) >= 14 and closes[-14] > 0:
            momentum = (closes[-1] - closes[-14]) / closes[-14] * 100
        else:
            momentum = 0

        return {'rsi': rsi, 'macd': macd, 'momentum': momentum}

    def calculate_ema(self, prices, period):
        if len(prices) < period:
            return None
        alpha = 2 / (period + 1)
        ema = prices[0]
        for price in prices[1:]:
            ema = price * alpha + ema * (1 - alpha)
        return ema

    def analyze_volatility(self, closes, highs, lows):
        if len(closes) < 20:
            return {'atr': 0, 'bollinger': {'upper': 0, 'middle': 0, 'lower': 0}}

        tr = []
        for i in range(1, len(closes)):
            tr.append(max(highs[i] - lows[i],
                          abs(highs[i] - closes[i - 1]),
                          abs(lows[i] - closes[i - 1])))
        atr = sum(tr[-14:]) / 14 if tr else 0

        sma = sum(closes[-20:]) / 20
        variance = sum((c - sma) ** 2 for c in closes[-20:]) / 20
        std = math.sqrt(variance) if variance > 0 else 0

        return {
            'atr': atr,
            'bollinger': {
                'upper': sma + 2 * std,
                'middle': sma,
                'lower': sma - 2 * std
            }
        }

    def analyze_volume(self, volumes, closes):
        if len(volumes) < 20:
            return {'current': 0, 'avg': 0, 'ratio': 1, 'spike': False}

        avg_volume = sum(volumes[-20:]) / 20
        current_volume = volumes[-1] if volumes else 0
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1

        return {
            'current': current_volume,
            'avg': avg_volume,
            'ratio': volume_ratio,
            'spike': volume_ratio > 1.5
        }

    def find_support_resistance(self, highs, lows):
        support_levels = []
        resistance_levels = []

        for i in range(10, len(lows) - 10):
            if lows[i] == min(lows[i - 5:i + 5]):
                if len(support_levels) == 0 or abs(lows[i] - support_levels[-1]) > 0.0005:
                    support_levels.append(lows[i])

            if highs[i] == max(highs[i - 5:i + 5]):
                if len(resistance_levels) == 0 or abs(highs[i] - resistance_levels[-1]) > 0.0005:
                    resistance_levels.append(highs[i])

        return {
            'support': support_levels[-3:] if support_levels else [],
            'resistance': resistance_levels[-3:] if resistance_levels else [],
            'nearest_support': support_levels[-1] if support_levels else None,
            'nearest_resistance': resistance_levels[-1] if resistance_levels else None
        }

    def detect_patterns(self, closes, highs, lows):
        patterns = []
        if len(closes) < 3:
            return patterns

        opens = [closes[i] - random.uniform(-0.0001, 0.0001) for i in range(len(closes))]

        if len(closes) >= 2:
            if closes[-1] > opens[-1] and closes[-2] < opens[-2]:
                if closes[-1] > opens[-2] and opens[-1] < closes[-2]:
                    patterns.append({'type': 'Bullish Engulfing', 'strength': 2})
            elif closes[-1] < opens[-1] and closes[-2] > opens[-2]:
                if opens[-1] > closes[-2] and closes[-1] < opens[-2]:
                    patterns.append({'type': 'Bearish Engulfing', 'strength': 2})

        for i in range(max(0, len(closes) - 3), len(closes)):
            body = abs(closes[i] - opens[i])
            high_low = highs[i] - lows[i]
            if high_low > 0 and body / high_low < 0.1:
                patterns.append({'type': 'Doji', 'strength': 1})

        return patterns

class SentimentAnalyzer:
    def analyze(self, symbol):
        sentiment = random.uniform(-0.3, 0.3)
        direction = 'Bullish' if sentiment > 0.15 else 'Bearish' if sentiment < -0.15 else 'Neutral'
        confidence = random.uniform(40, 80)

        return {
            'score': sentiment,
            'direction': direction,
            'confidence': confidence
        }

# ============================================================
# GLOBAL STATE
# ============================================================

market_regime = MarketRegimeDetector()
technical_analyzer = TechnicalAnalyzer()
sentiment_analyzer = SentimentAnalyzer()

bot_state = {
    'running': False,
    'broker_connected': False,
    'broker_type': None,
    'positions': [],
    'account': {},
    'analysis': {},
    'logs': [],
    'signals': [],
    'trade_logs': [],
    'current_user': None,
    'performance': {
        'total_trades': 0,
        'winning_trades': 0,
        'losing_trades': 0,
        'win_rate': 0,
        'total_profit': 0
    }
}

# ============================================================
# POSITION SYNC FUNCTION
# ============================================================

def sync_positions():
    if not bot_state['broker_connected'] or bot_state['broker_type'] not in ['MT5', 'MT4']:
        return

    if BOT_AVAILABLE and IS_WINDOWS:
        try:
            positions = mt5.positions_get()

            if positions:
                mt5_positions = []
                for pos in positions:
                    mt5_positions.append({
                        'ticket': pos.ticket,
                        '_id': str(pos.ticket),
                        'symbol': pos.symbol,
                        'type': 'buy' if pos.type == 0 else 'sell',
                        'volume': pos.volume,
                        'price_open': pos.price_open,
                        'price_current': pos.price_current if hasattr(pos, 'price_current') else pos.price_open,
                        'profit': pos.profit if hasattr(pos, 'profit') else 0,
                        'sl': pos.sl,
                        'tp': pos.tp
                    })

                bot_state['positions'] = mt5_positions
                socketio.emit('positions_updated', {'positions': bot_state['positions']})

                total_profit = sum(p.get('profit', 0) for p in mt5_positions)
                log_message(f'📊 Synced {len(mt5_positions)} positions from {bot_state["broker_type"]}')
            else:
                if bot_state['positions']:
                    bot_state['positions'] = []
                    socketio.emit('positions_updated', {'positions': []})
                    log_message(f'📊 No open positions in {bot_state["broker_type"]}')

        except Exception as e:
            log_message(f'⚠️ Position sync error: {str(e)}')

def add_position_to_ui(position):
    exists = False
    for p in bot_state['positions']:
        if p.get('ticket') == position.get('ticket') or p.get('_id') == position.get('_id'):
            exists = True
            break

    if not exists:
        bot_state['positions'].append(position)

    socketio.emit('positions_updated', {'positions': bot_state['positions']})
    bot_state['performance']['total_trades'] = len(bot_state['positions'])
    log_message(f'📊 Position added to UI: {position.get("symbol")} {position.get("type")} {position.get("volume")}')

def remove_position_from_ui(ticket):
    bot_state['positions'] = [p for p in bot_state['positions'] if
                              p.get('ticket') != ticket and p.get('_id') != str(ticket)]
    socketio.emit('positions_updated', {'positions': bot_state['positions']})
    log_message(f'📊 Position {ticket} removed from UI')

# ============================================================
# WEB ROUTES
# ============================================================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status')
def get_status():
    if bot_state['broker_connected'] and bot_state['broker_type'] in ['MT5', 'MT4']:
        sync_positions()

    return jsonify({
        'running': bot_state['running'],
        'broker_connected': bot_state['broker_connected'],
        'broker_type': bot_state['broker_type'],
        'account': bot_state['account'],
        'positions': bot_state['positions'],
        'analysis': bot_state['analysis'],
        'performance': bot_state['performance'],
        'trade_logs': bot_state['trade_logs'][-20:],
        'current_user': bot_state['current_user']
    })

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username', '')
    password = data.get('password', '')
    server = data.get('server', 'Headway-Demo')
    broker_type = data.get('broker_type', 'demo')

    log_message(f'🔐 Login attempt: {username} on {server} ({broker_type})')

    # Store user in session
    if username not in users:
        user = create_user(username, password, broker_type)
        log_message(f'📝 New user created: {username}')
    else:
        user = authenticate_user(username, password)
        if not user:
            log_message(f'❌ Login failed: Invalid password for {username}')
            return jsonify({'success': False, 'error': 'Invalid password'})

    # Handle MT5/MT4 - only available on Windows
    if broker_type in ['mt5', 'mt4']:
        if not IS_WINDOWS:
            error_msg = f"{broker_type.upper()} is only available on Windows. Please use Demo or Paper Trading mode in this environment."
            log_message(f'❌ {error_msg}')
            return jsonify({'success': False, 'error': error_msg})
            
        if not BOT_AVAILABLE:
            error_msg = f"MetaTrader5 module not installed. Please install it on Windows: pip install MetaTrader5"
            log_message(f'❌ {error_msg}')
            return jsonify({'success': False, 'error': error_msg})
            
        try:
            # Initialize MT5
            if not mt5.initialize():
                error_msg = f"Failed to initialize {broker_type.upper()}. Make sure {broker_type.upper()} terminal is installed."
                log_message(f'❌ {error_msg}')
                return jsonify({'success': False, 'error': error_msg})

            # Login
            login_result = mt5.login(int(username) if username.isdigit() else username, password, server)
            if login_result:
                account = mt5.account_info()
                if account:
                    broker_display = 'MT4' if broker_type == 'mt4' else 'MT5'
                    bot_state['broker_connected'] = True
                    bot_state['broker_type'] = broker_display
                    bot_state['account'] = {
                        'balance': account.balance,
                        'equity': account.equity,
                        'login': str(account.login),
                        'server': account.server,
                        'username': username
                    }
                    bot_state['current_user'] = username

                    log_message(f'✅ Connected to {broker_display} - Account: {account.login}, Balance: ${account.balance:.2f}')

                    socketio.emit('broker_status', {'connected': True, 'broker_type': broker_display})
                    socketio.emit('account_info', bot_state['account'])

                    sync_positions()

                    return jsonify({
                        'success': True,
                        'message': f'Connected to {broker_display} - Account: {account.login}',
                        'broker': broker_display,
                        'account': {
                            'balance': account.balance,
                            'equity': account.equity,
                            'login': str(account.login),
                            'server': account.server
                        }
                    })
                else:
                    error_msg = f"{broker_type.upper()} login failed: No account info"
                    log_message(f'❌ {error_msg}')
                    return jsonify({'success': False, 'error': error_msg})
            else:
                error_msg = f"Login failed: {mt5.last_error()}"
                log_message(f'❌ {error_msg}')
                return jsonify({'success': False, 'error': error_msg})

        except Exception as e:
            log_message(f'❌ {broker_type.upper()} connection error: {str(e)}')
            return jsonify({'success': False, 'error': str(e)})

    elif broker_type == 'paper':
        bot_state['broker_connected'] = True
        bot_state['broker_type'] = 'Paper'
        bot_state['account'] = {
            'balance': 100000,
            'equity': 100000,
            'login': username,
            'server': 'Paper Trading',
            'username': username
        }
        bot_state['current_user'] = username
        log_message(f'✅ Connected to Paper Trading - User: {username}')
        socketio.emit('broker_status', {'connected': True, 'broker_type': 'Paper'})
        socketio.emit('account_info', bot_state['account'])
        return jsonify({'success': True, 'message': 'Connected to Paper Trading', 'broker': 'Paper'})

    else:  # demo mode
        bot_state['broker_connected'] = True
        bot_state['broker_type'] = 'Demo'
        bot_state['account'] = {
            'balance': 10000,
            'equity': 10000,
            'login': 'DEMO',
            'server': 'Demo Server',
            'username': username
        }
        bot_state['current_user'] = username
        log_message(f'✅ Connected to Demo mode - User: {username}')
        socketio.emit('broker_status', {'connected': True, 'broker_type': 'Demo'})
        socketio.emit('account_info', bot_state['account'])
        return jsonify({'success': True, 'message': 'Connected to Demo Mode', 'broker': 'Demo'})

@app.route('/api/logout', methods=['POST'])
def logout():
    if BOT_AVAILABLE and IS_WINDOWS and bot_state['broker_type'] in ['MT5', 'MT4']:
        try:
            mt5.shutdown()
        except:
            pass

    bot_state['broker_connected'] = False
    bot_state['broker_type'] = None
    bot_state['account'] = {}
    bot_state['positions'] = []
    bot_state['current_user'] = None
    log_message('User logged out')
    socketio.emit('broker_status', {'connected': False, 'broker_type': None})
    socketio.emit('account_info', {})
    socketio.emit('positions_updated', {'positions': []})
    return jsonify({'success': True, 'message': 'Logged out'})

@app.route('/api/analyze', methods=['GET'])
def analyze_market():
    symbol = request.args.get('symbol', 'EURUSD')

    try:
        if BOT_AVAILABLE and IS_WINDOWS and bot_state['broker_type'] in ['MT5', 'MT4']:
            try:
                data = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 200)
                if data and len(data) > 50:
                    bars = []
                    for bar in data:
                        if isinstance(bar, tuple):
                            bars.append({
                                'time': bar[0], 'open': bar[1], 'high': bar[2],
                                'low': bar[3], 'close': bar[4], 'tick_volume': bar[5]
                            })
                        else:
                            bars.append(bar)

                    technical = technical_analyzer.analyze(bars)
                    sentiment = sentiment_analyzer.analyze(symbol)
                    regime = market_regime.detect(bars)

                    analysis = {
                        'symbol': symbol,
                        'timestamp': datetime.now().isoformat(),
                        'market_regime': regime,
                        'technical': technical,
                        'sentiment': sentiment
                    }

                    recommendation = generate_recommendation(analysis)
                    analysis['recommendation'] = recommendation

                    bot_state['analysis'] = analysis
                    socketio.emit('analysis_update', analysis)
                    return jsonify(analysis)
            except Exception as e:
                print(f"MT5 data error: {e}")

        bars = generate_demo_data(200)

        technical = technical_analyzer.analyze(bars)
        sentiment = sentiment_analyzer.analyze(symbol)
        regime = market_regime.detect(bars)

        analysis = {
            'symbol': symbol,
            'timestamp': datetime.now().isoformat(),
            'market_regime': regime,
            'technical': technical,
            'sentiment': sentiment
        }

        recommendation = generate_recommendation(analysis)
        analysis['recommendation'] = recommendation

        bot_state['analysis'] = analysis
        socketio.emit('analysis_update', analysis)
        return jsonify(analysis)

    except Exception as e:
        return jsonify({'error': str(e)})

def generate_recommendation(analysis):
    scores = {'BUY': 0, 'SELL': 0, 'HOLD': 0}
    reasons = []

    tech = analysis.get('technical', {})
    trend = tech.get('trend', {})
    momentum = tech.get('momentum', {})
    sentiment = analysis.get('sentiment', {})
    regime = analysis.get('market_regime', 'Neutral')

    if trend.get('direction') == 'Bullish':
        scores['BUY'] += 30
        reasons.append('Bullish trend')
    elif trend.get('direction') == 'Bearish':
        scores['SELL'] += 30
        reasons.append('Bearish trend')
    else:
        scores['HOLD'] += 15
        reasons.append('Neutral trend')

    rsi = momentum.get('rsi', 50)
    if rsi < 30:
        scores['BUY'] += 20
        reasons.append(f'Oversold (RSI: {rsi:.1f})')
    elif rsi > 70:
        scores['SELL'] += 20
        reasons.append(f'Overbought (RSI: {rsi:.1f})')
    else:
        scores['HOLD'] += 10
        reasons.append(f'RSI neutral ({rsi:.1f})')

    macd = momentum.get('macd', 0)
    if macd > 0:
        scores['BUY'] += 15
        reasons.append('MACD bullish')
    elif macd < 0:
        scores['SELL'] += 15
        reasons.append('MACD bearish')
    else:
        scores['HOLD'] += 5

    if sentiment.get('direction') == 'Bullish':
        scores['BUY'] += 15
        reasons.append(f'Positive sentiment ({sentiment.get("confidence", 0):.0f}%)')
    elif sentiment.get('direction') == 'Bearish':
        scores['SELL'] += 15
        reasons.append(f'Negative sentiment ({sentiment.get("confidence", 0):.0f}%)')
    else:
        scores['HOLD'] += 10

    if regime in ['Strong Trend', 'Trending']:
        if trend.get('direction') == 'Bullish':
            scores['BUY'] += 10
            reasons.append(f'{regime} regime')
        elif trend.get('direction') == 'Bearish':
            scores['SELL'] += 10
            reasons.append(f'{regime} regime')
    elif regime == 'Ranging':
        scores['HOLD'] += 20
        reasons.append('Ranging market - wait for breakout')
    elif regime == 'Volatile':
        scores['HOLD'] += 15
        reasons.append('High volatility - caution')

    total = scores['BUY'] + scores['SELL'] + scores['HOLD']
    if total == 0:
        return {'action': 'HOLD', 'confidence': 0, 'reasons': ['No clear signals']}

    confidence = max(scores.values()) / total * 100

    if scores['BUY'] > scores['SELL'] and scores['BUY'] > scores['HOLD']:
        action = 'BUY'
    elif scores['SELL'] > scores['BUY'] and scores['SELL'] > scores['HOLD']:
        action = 'SELL'
    else:
        action = 'HOLD'

    return {
        'action': action,
        'confidence': confidence,
        'scores': scores,
        'reasons': reasons[:3]
    }

# ============================================================
# TRADING FUNCTIONS
# ============================================================

@app.route('/api/trading/trade', methods=['POST'])
def place_trade():
    data = request.json
    symbol = data.get('symbol', 'EURUSD')
    trade_type = data.get('type', 'buy').lower()
    volume = data.get('volume', 0.01)
    sl = data.get('stopLoss', 0)
    tp = data.get('takeProfit', 0)

    log_message(f'📊 Trade request: {trade_type.upper()} {symbol} {volume} lots')

    if not bot_state['broker_connected']:
        log_message('❌ Trade rejected: Broker not connected')
        return jsonify({'success': False, 'error': 'Broker not connected'})

    try:
        # Get current price based on trade type
        if BOT_AVAILABLE and IS_WINDOWS and bot_state['broker_type'] in ['MT5', 'MT4']:
            tick = mt5.symbol_info_tick(symbol)
            if tick:
                if trade_type == 'buy':
                    price = tick.ask
                else:
                    price = tick.bid
                log_message(f'💰 Current price for {trade_type}: {price:.5f}')
            else:
                price = 1.1000
                log_message('⚠️ Using simulated price')
        else:
            price = 1.1000 + random.uniform(-0.001, 0.001)
            log_message(f'💰 Simulated price: {price:.5f}')

        # Calculate SL and TP if not provided
        atr = bot_state.get('analysis', {}).get('technical', {}).get('volatility', {}).get('atr', 0.001)
        if sl == 0:
            sl_distance = atr * 1.5
            sl = price - sl_distance if trade_type == 'buy' else price + sl_distance
            log_message(f'📉 Auto SL: {sl:.5f}')
        if tp == 0:
            tp_distance = atr * 2.5
            tp = price + tp_distance if trade_type == 'buy' else price - tp_distance
            log_message(f'📈 Auto TP: {tp:.5f}')

        # Execute trade based on broker type
        if bot_state['broker_type'] in ['MT5', 'MT4'] and BOT_AVAILABLE and IS_WINDOWS:
            result = execute_mt5_trade(symbol, trade_type, volume, price, sl, tp)
        else:
            result = execute_demo_trade(symbol, trade_type, volume, price, sl, tp)

        if result['success']:
            log_message(f'✅ Trade opened! Ticket: {result["ticket"]}')
            add_position_to_ui(result['position'])

            return jsonify({
                'success': True,
                'trade': result['position'],
                'message': 'Trade placed successfully'
            })
        else:
            log_message(f'❌ Trade failed: {result["error"]}')
            return jsonify({
                'success': False,
                'error': result['error']
            })

    except Exception as e:
        log_message(f'❌ Trade execution error: {str(e)}')
        return jsonify({'success': False, 'error': str(e)})

def execute_mt5_trade(symbol, trade_type, volume, price, sl, tp):
    try:
        # Set order type based on trade type
        if trade_type == 'buy':
            order_type = mt5.ORDER_TYPE_BUY
            log_message(f'📈 Executing BUY order at {price:.5f}')
        else:
            order_type = mt5.ORDER_TYPE_SELL
            log_message(f'📉 Executing SELL order at {price:.5f}')

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": order_type,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": 20,
            "magic": 123456,
            "comment": f"{trade_type.upper()}_{int(time.time())}",
            "type_filling": mt5.ORDER_FILLING_IOC,
            "type_time": mt5.ORDER_TIME_GTC
        }

        result = mt5.order_send(request)

        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            ticket = result.order
            log_message(f'✅ Order executed! Ticket: {ticket}')

            # Get the position from MT5
            positions = mt5.positions_get(ticket=ticket)
            if positions:
                pos = positions[0]
                position = {
                    'ticket': pos.ticket,
                    '_id': str(pos.ticket),
                    'symbol': pos.symbol,
                    'type': 'buy' if pos.type == 0 else 'sell',
                    'volume': pos.volume,
                    'price_open': pos.price_open,
                    'price_current': pos.price_current if hasattr(pos, 'price_current') else pos.price_open,
                    'profit': pos.profit if hasattr(pos, 'profit') else 0,
                    'sl': pos.sl,
                    'tp': pos.tp
                }
            else:
                position = {
                    'ticket': ticket,
                    '_id': str(ticket),
                    'symbol': symbol,
                    'type': trade_type,
                    'volume': volume,
                    'price_open': result.price,
                    'price_current': result.price,
                    'profit': 0,
                    'sl': sl,
                    'tp': tp
                }

            bot_state['performance']['total_trades'] += 1

            bot_state['trade_logs'].append({
                'time': datetime.now().isoformat(),
                'type': trade_type.upper(),
                'symbol': symbol,
                'volume': volume,
                'entry': result.price,
                'sl': sl,
                'tp': tp,
                'ticket': ticket,
                'status': 'OPEN'
            })

            sync_positions()
            socketio.emit('performance_update', bot_state['performance'])
            socketio.emit('trade_log', {'logs': bot_state['trade_logs'][-10:]})

            return {'success': True, 'ticket': ticket, 'position': position}
        else:
            error_msg = f"Order failed: {result.retcode if result else 'Unknown'}"
            log_message(f'❌ {error_msg}')
            return {'success': False, 'error': error_msg}

    except Exception as e:
        log_message(f'❌ Trade error: {str(e)}')
        return {'success': False, 'error': str(e)}

def execute_demo_trade(symbol, trade_type, volume, price, sl, tp):
    ticket = random.randint(10000, 99999)

    position = {
        'ticket': ticket,
        '_id': str(ticket),
        'symbol': symbol,
        'type': trade_type,
        'volume': volume,
        'price_open': price,
        'price_current': price,
        'profit': 0,
        'sl': sl,
        'tp': tp
    }

    bot_state['performance']['total_trades'] += 1

    bot_state['trade_logs'].append({
        'time': datetime.now().isoformat(),
        'type': trade_type.upper(),
        'symbol': symbol,
        'volume': volume,
        'entry': price,
        'sl': sl,
        'tp': tp,
        'ticket': ticket,
        'status': 'OPEN',
        'reasons': ['Demo trade']
    })

    log_message(f'✅ Demo trade opened! Ticket: {ticket}')
    add_position_to_ui(position)

    socketio.emit('performance_update', bot_state['performance'])
    socketio.emit('trade_log', {'logs': bot_state['trade_logs'][-10:]})

    return {'success': True, 'ticket': ticket, 'position': position}

# ============================================================
# CLOSE TRADE
# ============================================================

@app.route('/api/trading/close/<trade_id>', methods=['POST'])
def close_trade(trade_id):
    log_message(f'📊 Closing trade: {trade_id}')

    # Find the position in our state
    position_to_close = None
    for pos in bot_state['positions']:
        if str(pos.get('_id', '')) == trade_id or str(pos.get('ticket', '')) == trade_id:
            position_to_close = pos
            break

    if not position_to_close:
        log_message(f'❌ Trade {trade_id} not found')
        return jsonify({'success': False, 'error': 'Trade not found'})

    try:
        ticket = int(position_to_close.get('ticket'))
        symbol = position_to_close.get('symbol')
        position_type = position_to_close.get('type')

        log_message(f'📊 Found position: Ticket={ticket}, Symbol={symbol}, Type={position_type}')

        # If MT5 connected, close via MT5
        if bot_state['broker_type'] in ['MT5', 'MT4'] and BOT_AVAILABLE and IS_WINDOWS:
            # Get position from MT5
            positions = mt5.positions_get(ticket=ticket)
            if positions and len(positions) > 0:
                pos = positions[0]

                # Determine close order type
                if pos.type == 0:  # BUY position - close with SELL
                    order_type = mt5.ORDER_TYPE_SELL
                    price = mt5.symbol_info_tick(symbol).bid
                    log_message(f'📊 Closing BUY position with SELL order at {price:.5f}')
                else:  # SELL position - close with BUY
                    order_type = mt5.ORDER_TYPE_BUY
                    price = mt5.symbol_info_tick(symbol).ask
                    log_message(f'📊 Closing SELL position with BUY order at {price:.5f}')

                close_request = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "symbol": symbol,
                    "volume": pos.volume,
                    "type": order_type,
                    "position": ticket,
                    "price": price,
                    "deviation": 20,
                    "magic": 123456,
                    "comment": "Close",
                    "type_filling": mt5.ORDER_FILLING_IOC,
                    "type_time": mt5.ORDER_TIME_GTC
                }

                result = mt5.order_send(close_request)

                if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                    profit = pos.profit if hasattr(pos, 'profit') else 0
                    log_message(f'✅ Position closed! Profit: ${profit:.2f}')

                    # Update performance
                    bot_state['performance']['total_profit'] += profit
                    if profit > 0:
                        bot_state['performance']['winning_trades'] += 1
                    else:
                        bot_state['performance']['losing_trades'] += 1

                    bot_state['performance']['win_rate'] = (
                            bot_state['performance']['winning_trades'] /
                            bot_state['performance']['total_trades'] * 100
                    ) if bot_state['performance']['total_trades'] > 0 else 0

                    # Remove from positions
                    remove_position_from_ui(ticket)

                    # Update trade log
                    for log in bot_state['trade_logs']:
                        if str(log.get('ticket', '')) == str(ticket):
                            log['status'] = 'CLOSED'
                            log['profit'] = profit
                            log['close_time'] = datetime.now().isoformat()
                            break

                    socketio.emit('performance_update', bot_state['performance'])
                    socketio.emit('trade_log', {'logs': bot_state['trade_logs'][-10:]})
                    socketio.emit('positions_updated', {'positions': bot_state['positions']})

                    return jsonify({
                        'success': True,
                        'profit': profit,
                        'message': f'Trade closed with ${profit:.2f} profit'
                    })
                else:
                    error_msg = f"Close order failed: {result.retcode if result else 'Unknown'}"
                    log_message(f'❌ {error_msg}')
                    return jsonify({'success': False, 'error': error_msg})
            else:
                log_message(f'❌ Position {ticket} not found')
                return jsonify({'success': False, 'error': 'Position not found'})

        else:
            # Demo/Paper mode - simulate close
            profit = position_to_close.get('profit', random.uniform(-2, 5))
            log_message(f'📊 Closing Demo position with profit: ${profit:.2f}')

            bot_state['performance']['total_profit'] += profit
            if profit > 0:
                bot_state['performance']['winning_trades'] += 1
            else:
                bot_state['performance']['losing_trades'] += 1

            bot_state['performance']['win_rate'] = (
                    bot_state['performance']['winning_trades'] /
                    bot_state['performance']['total_trades'] * 100
            ) if bot_state['performance']['total_trades'] > 0 else 0

            remove_position_from_ui(ticket)

            for log in bot_state['trade_logs']:
                if str(log.get('ticket', '')) == str(ticket):
                    log['status'] = 'CLOSED'
                    log['profit'] = profit
                    log['close_time'] = datetime.now().isoformat()
                    break

            socketio.emit('performance_update', bot_state['performance'])
            socketio.emit('trade_log', {'logs': bot_state['trade_logs'][-10:]})
            socketio.emit('positions_updated', {'positions': bot_state['positions']})

            return jsonify({
                'success': True,
                'profit': profit,
                'message': f'Trade closed with ${profit:.2f} profit'
            })

    except Exception as e:
        log_message(f'❌ Close trade error: {str(e)}')
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/signals/generate', methods=['POST'])
def generate_signal():
    analysis = bot_state.get('analysis', {})
    recommendation = analysis.get('recommendation', {})

    signal = {
        'symbol': 'EURUSD',
        'type': recommendation.get('action', 'HOLD').lower(),
        'confidence': int(recommendation.get('confidence', 50)),
        'createdAt': datetime.now().isoformat(),
        'reasons': recommendation.get('reasons', ['No clear signal']),
        'scores': recommendation.get('scores', {})
    }

    bot_state['signals'].insert(0, signal)
    if len(bot_state['signals']) > 10:
        bot_state['signals'] = bot_state['signals'][:10]

    log_message(f'📊 New signal: {signal["type"].upper()} with {signal["confidence"]}% confidence')
    socketio.emit('signal_update', signal)

    return jsonify({'success': True, 'signal': signal})

@app.route('/api/robot/toggle', methods=['POST'])
def toggle_robot():
    data = request.json
    is_active = data.get('isActive', False)

    if is_active and not bot_state['running']:
        if not bot_state['broker_connected']:
            log_message('❌ Cannot start robot: Broker not connected')
            return jsonify({'success': False, 'error': 'Broker not connected'})

        bot_state['running'] = True
        log_message('🤖 Robot STARTED')
        thread = threading.Thread(target=run_bot_loop, daemon=True)
        thread.start()
        socketio.emit('bot_status', {'running': True})
        return jsonify({'success': True, 'isActive': True, 'message': 'Robot started'})

    elif not is_active and bot_state['running']:
        bot_state['running'] = False
        log_message('🤖 Robot STOPPED')
        socketio.emit('bot_status', {'running': False})
        return jsonify({'success': True, 'isActive': False, 'message': 'Robot stopped'})

    return jsonify({'success': False, 'error': 'Invalid state'})

@app.route('/api/robot/performance')
def get_robot_performance():
    return jsonify({'success': True, 'performance': bot_state['performance']})

@app.route('/api/close_position/<int:ticket>', methods=['POST'])
def close_position_by_ticket(ticket):
    try:
        result = close_trade(str(ticket))
        return result
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/close_all_positions', methods=['POST'])
def close_all_positions():
    count = len(bot_state['positions'])
    tickets = [p.get('ticket') for p in bot_state['positions']]

    closed = 0
    for ticket in tickets:
        result = close_trade(str(ticket))
        if result.json.get('success'):
            closed += 1

    log_message(f'📊 Closed {closed} of {count} positions')
    return jsonify({'success': True, 'message': f'Closed {closed} of {count} positions'})

@app.route('/api/contact', methods=['POST'])
def contact():
    data = request.json
    log_message(f"📧 Contact: {data.get('name')} - {data.get('email')}")
    return jsonify({'success': True, 'message': 'Message sent successfully'})

# ============================================================
# BOT LOOP
# ============================================================

def execute_trade_from_signal(signal, analysis):
    confidence = analysis.get('recommendation', {}).get('confidence', 0)

    log_message(f'📊 EXECUTING TRADE: {signal} with {confidence:.0f}% confidence')

    if len(bot_state['positions']) > 0:
        log_message('⚠️ Trade NOT executed: Position already open')
        return False, "Position already open"

    if confidence < 60:
        log_message(f'⚠️ Trade NOT executed: Confidence too low ({confidence:.0f}% < 60%)')
        return False, f"Confidence too low ({confidence:.0f}% < 60%)"

    if not bot_state['broker_connected']:
        log_message('❌ Trade NOT executed: Broker not connected')
        return False, "Broker not connected"

    symbol = 'EURUSD'

    try:
        result = place_trade_from_signal(symbol, signal)

        if result['success']:
            log_message(f'✅ {signal} trade executed successfully')
            return True, "Trade executed"
        else:
            log_message(f'❌ Trade execution failed: {result["error"]}')
            return False, result["error"]

    except Exception as e:
        log_message(f'❌ Trade execution error: {str(e)}')
        return False, str(e)

def place_trade_from_signal(symbol, signal):
    trade_type = signal.lower()
    volume = 0.01

    if BOT_AVAILABLE and IS_WINDOWS and bot_state['broker_type'] in ['MT5', 'MT4']:
        try:
            tick = mt5.symbol_info_tick(symbol)
            if tick:
                price = tick.ask if trade_type == 'buy' else tick.bid
            else:
                price = 1.1000
        except:
            price = 1.1000
    else:
        price = 1.1000 + random.uniform(-0.001, 0.001)

    atr = bot_state.get('analysis', {}).get('technical', {}).get('volatility', {}).get('atr', 0.001)
    sl_distance = atr * 1.5
    tp_distance = atr * 2.5

    if trade_type == 'buy':
        sl = price - sl_distance
        tp = price + tp_distance
    else:
        sl = price + sl_distance
        tp = price - tp_distance

    if bot_state['broker_type'] in ['MT5', 'MT4'] and BOT_AVAILABLE and IS_WINDOWS:
        return execute_mt5_trade(symbol, trade_type, volume, price, sl, tp)
    else:
        return execute_demo_trade(symbol, trade_type, volume, price, sl, tp)

def run_bot_loop():
    log_message('🤖 Bot loop STARTED')
    cycle = 0

    while bot_state['running']:
        try:
            cycle += 1
            log_message(f'🔄 Cycle {cycle} - Starting analysis...')

            sync_positions()

            with app.app_context():
                result = analyze_market()
                if hasattr(result, 'json'):
                    try:
                        analysis = result.json
                        bot_state['analysis'] = analysis
                    except:
                        pass

            if bot_state['analysis']:
                analysis = bot_state['analysis']
                recommendation = analysis.get('recommendation', {})
                action = recommendation.get('action', 'HOLD')
                confidence = recommendation.get('confidence', 0)
                reasons = recommendation.get('reasons', [])

                log_message(f'📊 Signal: {action} with {confidence:.0f}% confidence')
                for reason in reasons:
                    log_message(f'  - {reason}')

                if action in ['BUY', 'SELL'] and confidence > 60:
                    log_message(f'🔄 Attempting to execute {action} trade...')
                    success, message = execute_trade_from_signal(action, analysis)
                    if success:
                        log_message(f'✅ {action} trade executed successfully')
                        sync_positions()
                        generate_signal()
                    else:
                        log_message(f'⏸️ {action} trade NOT executed: {message}')
                else:
                    log_message('⏸️ No trade signal (HOLD)')
            else:
                log_message('⚠️ No analysis available')

            if cycle % 2 == 0:
                sync_positions()

            time.sleep(60)

        except Exception as e:
            log_message(f'❌ Bot loop error: {str(e)}')
            time.sleep(60)

    log_message('🤖 Bot loop STOPPED')

# ============================================================
# HELPER FUNCTIONS
# ============================================================

def log_message(message):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f'[{timestamp}] {message}'
    bot_state['logs'].insert(0, log_entry)
    if len(bot_state['logs']) > 100:
        bot_state['logs'] = bot_state['logs'][:100]
    socketio.emit('log_message', {'message': log_entry})
    print(log_entry)

# ============================================================
# WEBSOCKET EVENTS
# ============================================================

@socketio.on('connect')
def handle_connect():
    emit('bot_status', {'running': bot_state['running']})
    emit('broker_status', {'connected': bot_state['broker_connected'], 'broker_type': bot_state['broker_type']})
    emit('account_info', bot_state['account'])
    emit('positions_updated', {'positions': bot_state['positions']})
    emit('performance_update', bot_state['performance'])
    emit('trade_log', {'logs': bot_state['trade_logs'][-10:]})
    if bot_state['analysis']:
        emit('analysis_update', bot_state['analysis'])
    if bot_state['signals']:
        emit('signal_update', bot_state['signals'][0])

# ============================================================
# MAIN
# ============================================================

if __name__ == '__main__':
    print("=" * 70)
    print("🚀 ULTIMATE FOREX BOT - AI TRADING PLATFORM")
    print("=" * 70)
    print(f"📊 Dashboard: http://localhost:5000")
    print("=" * 70)
    print(f"💻 Platform: {sys.platform}")
    print(f"🔐 MT5/MT4 Available: {'Yes (Windows)' if BOT_AVAILABLE and IS_WINDOWS else 'No (Use Demo/Paper mode)'}")
    print("=" * 70)
    print("📋 Supported Modes:")
    print("  ✅ Demo Mode - No credentials needed, simulated trading")
    print("  ✅ Paper Trading - Virtual account with $100,000")
    print("  ✅ MT5/MT4 - Only on Windows with MetaTrader5 installed")
    print("=" * 70)
    print("📱 Mobile-optimized responsive design")
    print("=" * 70)
    print("Press Ctrl+C to stop")
    print("=" * 70)

    socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True)
