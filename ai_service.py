import google.generativeai as genai
import os
from dotenv import load_dotenv
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import logging
import time
import traceback
import json
import numpy as np
import pickle
from datetime import datetime, timedelta
import sqlite3
from transformers import AutoTokenizer, AutoModel, pipeline
import torch
import re
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
import pandas as pd

# Cấu hình logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('depression_support.log')
    ]
)
logger = logging.getLogger(__name__)

# Tải biến môi trường từ file .env
load_dotenv()

app = Flask(__name__)
CORS(app)

# Cấu hình Google AI
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
if not GOOGLE_API_KEY:
    raise ValueError("Không tìm thấy GOOGLE_API_KEY. Hãy chắc chắn bạn đã tạo file .env")

try:
    genai.configure(api_key=GOOGLE_API_KEY)
    logger.info("Đã cấu hình Google AI thành công")
except Exception as e:
    logger.error(f"Lỗi cấu hình Google AI: {e}")
    raise

# Khởi tạo database để lưu lịch sử và tracking
def init_database():
    conn = sqlite3.connect('depression_support.db')
    cursor = conn.cursor()
    
    # Bảng lưu lịch sử chat
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            message TEXT,
            response TEXT,
            sentiment_score REAL,
            depression_indicators TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Bảng lưu thông tin theo dõi người dùng
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_tracking (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            mood_score REAL,
            depression_level TEXT,
            recommended_actions TEXT,
            last_check DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Bảng lưu resources hỗ trợ
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS support_resources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT,
            title TEXT,
            description TEXT,
            contact_info TEXT,
            emergency BOOLEAN DEFAULT 0
        )
    ''')
    
    conn.commit()
    conn.close()

# Khởi tạo database
init_database()

# Load PhoBERT model để phân tích sentiment và nội dung tiếng Việt
class VietnameseNLPProcessor:
    def __init__(self):
        try:
            # Load PhoBERT model cho tiếng Việt
            self.phobert_tokenizer = AutoTokenizer.from_pretrained("vinai/phobert-base")
            self.phobert_model = AutoModel.from_pretrained("vinai/phobert-base")
            
            # Load Vietnamese sentiment analysis pipeline
            self.sentiment_analyzer = pipeline(
                "sentiment-analysis",
                model="cardiffnlp/twitter-roberta-base-sentiment-latest"
            )
            
            # Depression keywords và patterns
            self.depression_keywords = [
                'buồn', 'tuyệt vọng', 'chán nản', 'stress', 'lo lắng', 'cô đơn',
                'mệt mỏi', 'không có ý nghĩa', 'thất vọng', 'trầm cảm', 'tự tử',
                'khóc', 'mất ngủ', 'không ăn được', 'tự ti', 'vô dụng',
                'không ai hiểu', 'cuộc sống khó khăn', 'áp lực', 'đau khổ'
            ]
            
            # Positive emotion keywords
            self.positive_keywords = [
                'vui vẻ', 'hạnh phúc', 'tích cực', 'hy vọng', 'yêu thương',
                'thành công', 'tự tin', 'mạnh mẽ', 'biết ơn', 'sáng tạo'
            ]
            
            logger.info("Đã khởi tạo Vietnamese NLP Processor thành công")
        except Exception as e:
            logger.error(f"Lỗi khởi tạo Vietnamese NLP Processor: {e}")
            raise

    def analyze_sentiment(self, text):
        """Phân tích cảm xúc của văn bản"""
        try:
            # Đếm từ khóa tiêu cực và tích cực
            depression_count = sum(1 for keyword in self.depression_keywords if keyword in text.lower())
            positive_count = sum(1 for keyword in self.positive_keywords if keyword in text.lower())
            
            # Tính điểm sentiment (-1 đến 1)
            if depression_count > positive_count:
                sentiment_score = -0.7 * (depression_count / len(text.split()))
            elif positive_count > depression_count:
                sentiment_score = 0.7 * (positive_count / len(text.split()))
            else:
                sentiment_score = 0.0
            
            # Đảm bảo điểm nằm trong khoảng [-1, 1]
            sentiment_score = max(-1, min(1, sentiment_score))
            
            return {
                'score': sentiment_score,
                'depression_indicators': depression_count,
                'positive_indicators': positive_count,
                'analysis': 'negative' if sentiment_score < -0.3 else 'positive' if sentiment_score > 0.3 else 'neutral'
            }
        except Exception as e:
            logger.error(f"Lỗi phân tích sentiment: {e}")
            return {'score': 0, 'depression_indicators': 0, 'positive_indicators': 0, 'analysis': 'neutral'}

    def extract_depression_indicators(self, text):
        """Trích xuất các dấu hiệu trầm cảm từ văn bản"""
        indicators = []
        
        # Patterns cho các dấu hiệu trầm cảm
        patterns = {
            'sleep_problems': r'(không ngủ được|mất ngủ|ngủ nhiều|ngủ không ngon)',
            'appetite_changes': r'(không ăn được|chán ăn|ăn nhiều|không có cảm giác đói)',
            'energy_loss': r'(mệt mỏi|kiệt sức|không có năng lượng|lười biếng)',
            'concentration_issues': r'(không tập trung|không thể suy nghĩ|trí nhớ kém)',
            'hopelessness': r'(tuyệt vọng|không có hy vọng|cuộc sống vô nghĩa)',
            'guilt_shame': r'(tự trách|cảm thấy tội lỗi|xấu hổ|tự ti)',
            'social_withdrawal': r'(cô đơn|không muốn gặp ai|tránh mọi người)',
            'suicidal_thoughts': r'(tự tử|chết đi|không muốn sống|kết thúc cuộc đời)'
        }
        
        for indicator, pattern in patterns.items():
            if re.search(pattern, text.lower()):
                indicators.append(indicator)
        
        return indicators

nlp_processor = VietnameseNLPProcessor()

# Recommendation System using BERT4Rec approach
class DepressionSupportRecommender:
    def __init__(self):
        self.activities = {
            'physical': [
                'Đi bộ 15-30 phút mỗi ngày trong công viên',
                'Tập yoga hoặc thiền định',
                'Tham gia hoạt động thể thao nhẹ nhàng',
                'Tập thở sâu và thư giãn',
                'Massage và chăm sóc bản thân'
            ],
            'social': [
                'Gọi điện cho người thân, bạn bè',
                'Tham gia các nhóm hỗ trợ',
                'Tham gia hoạt động tình nguyện',
                'Gặp gỡ bạn bè để trò chuyện',
                'Tham gia các lớp học hoặc câu lạc bộ'
            ],
            'creative': [
                'Viết nhật ký cảm xúc',
                'Vẽ tranh, tô màu',
                'Nghe nhạc thư giãn',
                'Đọc sách yêu thích',
                'Nấu ăn món mình thích'
            ],
            'professional': [
                'Tham khảo ý kiến bác sĩ tâm lý',
                'Liên hệ đường dây nóng hỗ trợ tâm lý',
                'Đặt lịch khám với chuyên gia sức khỏe tâm thần',
                'Tham gia liệu pháp nhóm',
                'Tìm hiểu về các phương pháp điều trị'
            ]
        }
        
        self.emergency_resources = {
            'hotlines': [
                {'name': 'Đường dây nóng Ngày Mai Tươi Sáng', 'number': '1800-8440', 'availability': '24/7, miễn phí'},
                {'name': 'Tư vấn tâm lý', 'number': '1900-1267', 'availability': '24/7'},
                {'name': 'Tổng đài sức khỏe tâm thần', 'number': '19001581', 'availability': '24/7, miễn phí'},
                {'name': 'Trung tâm Can thiệp Khủng hoảng', 'number': '0869-105-105', 'availability': '24/7'}
            ],
            'emergency_centers': [
                'Bệnh viện Tâm thần Trung ương 1',
                'Bệnh viện Tâm thần TP.HCM',
                'Trung tâm Sức khỏe Tâm thần Cộng đồng'
            ]
        }

    def recommend_activities(self, sentiment_analysis, depression_indicators):
        """Đề xuất hoạt động dựa trên phân tích tâm trạng"""
        recommendations = []
        
        # Phân loại mức độ trầm cảm
        if sentiment_analysis['score'] < -0.7 or len(depression_indicators) >= 4:
            level = 'severe'
        elif sentiment_analysis['score'] < -0.4 or len(depression_indicators) >= 2:
            level = 'moderate'
        else:
            level = 'mild'
        
        # Đề xuất dựa trên mức độ
        if level == 'severe':
            recommendations.extend(self.activities['professional'])
            recommendations.extend(self.activities['physical'][:2])
            recommendations.extend(self.activities['creative'][:2])
        elif level == 'moderate':
            recommendations.extend(self.activities['physical'][:3])
            recommendations.extend(self.activities['social'][:2])
            recommendations.extend(self.activities['creative'][:3])
        else:
            recommendations.extend(self.activities['physical'])
            recommendations.extend(self.activities['social'])
            recommendations.extend(self.activities['creative'])
        
        return recommendations[:5]  # Trả về tối đa 5 đề xuất

    def get_emergency_resources(self):
        """Lấy thông tin tài nguyên khẩn cấp"""
        return self.emergency_resources

recommender = DepressionSupportRecommender()

# Enhanced System Prompt với tính năng mới
ENHANCED_SYSTEM_PROMPT = """
Bạn là một trợ lý AI chuyên nghiệp có tên là IAmHere được đào tạo để hỗ trợ người có dấu hiệu trầm cảm. Bạn được tích hợp với các mô hình AI tiên tiến cho tiếng Việt bao gồm PhoBERT để hiểu sâu hơn về ngữ nghĩa và cảm xúc.

NHIỆM VỤ CHÍNH:
1. LẮNG NGHE VÀ THẤU HIỂU: Phản hồi với sự đồng cảm, không phán xét, tạo không gian an toàn
2. PHÂN TÍCH THÔNG MINH: Sử dụng AI để nhận diện các dấu hiệu trầm cảm một cách tinh tế
3. HỖ TRỢ CÁ NHÂN HÓA: Đưa ra lời khuyên phù hợp với tình trạng cụ thể của từng người
4. THEO DÕI TIẾN TRIỂN: Ghi nhận và theo dõi sự thay đổi tâm trạng qua thời gian
5. KẾT NỐI TÀI NGUYÊN: Cung cấp thông tin về các nguồn hỗ trợ chuyên nghiệp

NGUYÊN TắC HỖ TRỢ:
- KHÔNG BAO GIỜ chẩn đoán bệnh lý mà chỉ nhận diện dấu hiệu cần chú ý
- ƯU TIÊN an toàn: Luôn khuyến khích tìm kiếm giúp đỡ chuyên nghiệp khi cần
- TÍCH CỰC và HY VỌNG: Củng cố niềm tin vào khả năng phục hồi
- CÁ NHÂN HÓA: Điều chỉnh phương pháp hỗ trợ cho từng cá nhân
- BẢO MẬT: Tôn trọng sự riêng tư và không chia sẻ thông tin cá nhân

PHƯƠNG PHÁP HỖ TRỢ:
1. Kỹ thuật lắng nghe tích cực và phản ánh cảm xúc
2. Liệu pháp nhận thức hành vi (CBT) cơ bản
3. Kỹ thuật mindfulness và thư giãn
4. Xây dựng kế hoạch hành động thực tế
5. Tăng cường kết nối xã hội

TÀI NGUYÊN KHẨN CẤP (khi phát hiện nguy cơ tự hại):


HÃY TRẢ LỜI BẰNG TIẾNG VIỆT, SỬ DỤNG NGÔN NGỮ ẤM ÁP, DỄ HIỂU VÀ MANG TÍNH CHỮA LÀNH.
"""

# Chọn model Gemini
MODEL_NAME = 'gemini-1.5-flash-latest'
try:
    model = genai.GenerativeModel(MODEL_NAME)
    logger.info(f"Đã khởi tạo model {MODEL_NAME} thành công")
except Exception as e:
    logger.error(f"Lỗi khởi tạo model: {e}")
    raise

# Lưu trữ lịch sử chat với context mở rộng
chat_sessions = {}

def get_or_create_chat_session(user_id='default_user'):
    """Lấy hoặc tạo phiên chat cho người dùng"""
    if user_id not in chat_sessions:
        chat_sessions[user_id] = {
            'history': [
                {'role': 'user', 'parts': [ENHANCED_SYSTEM_PROMPT]},
                {'role': 'model', 'parts': ["Xin chào! Tôi là trợ lý AI được thiết kế đặc biệt để lắng nghe và hỗ trợ bạn trong những lúc khó khăn. Tôi được trang bị những công cụ AI tiên tiến để hiểu rõ hơn về cảm xúc và tình trạng tâm lý của bạn.\n\nBạn có thể chia sẻ bất cứ điều gì đang làm bạn lo lắng, buồn bã, hoặc khó chịu. Tôi sẽ lắng nghe mà không phán xét và cố gắng hỗ trợ bạn tốt nhất có thể.\n\nHôm nay bạn cảm thấy thế nào?"]}
            ],
            'mood_tracking': [],
            'last_activity': datetime.now()
        }
    return chat_sessions[user_id]

def save_chat_to_database(user_id, message, response, sentiment_analysis, depression_indicators):
    """Lưu cuộc trò chuyện vào database"""
    try:
        conn = sqlite3.connect('depression_support.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO chat_history (user_id, message, response, sentiment_score, depression_indicators)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            user_id,
            message,
            response,
            sentiment_analysis['score'],
            json.dumps(depression_indicators)
        ))
        
        conn.commit()
        conn.close()
        logger.info(f"Đã lưu cuộc trò chuyện cho user {user_id}")
    except Exception as e:
        logger.error(f"Lỗi lưu database: {e}")

def update_user_tracking(user_id, sentiment_analysis, recommendations):
    """Cập nhật thông tin theo dõi người dùng"""
    try:
        conn = sqlite3.connect('depression_support.db')
        cursor = conn.cursor()
        
        # Xác định mức độ trầm cảm
        score = sentiment_analysis['score']
        if score < -0.7:
            depression_level = 'severe'
        elif score < -0.4:
            depression_level = 'moderate'
        elif score < -0.1:
            depression_level = 'mild'
        else:
            depression_level = 'normal'
        
        cursor.execute('''
            INSERT OR REPLACE INTO user_tracking (user_id, mood_score, depression_level, recommended_actions, last_check)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            user_id,
            score,
            depression_level,
            json.dumps(recommendations),
            datetime.now()
        ))
        
        conn.commit()
        conn.close()
        logger.info(f"Đã cập nhật theo dõi cho user {user_id}")
    except Exception as e:
        logger.error(f"Lỗi cập nhật tracking: {e}")

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def enhanced_chat():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Không có dữ liệu JSON"}), 400
            
        user_input = data.get('message')
        user_id = data.get('user_id', 'default_user')
        
        if not user_input or not isinstance(user_input, str) or not user_input.strip():
            return jsonify({"error": "Tin nhắn không hợp lệ hoặc trống"}), 400

        logger.info(f"Nhận tin nhắn từ user {user_id}: {user_input[:50]}...")
        
        # Phân tích sentiment và dấu hiệu trầm cảm
        sentiment_analysis = nlp_processor.analyze_sentiment(user_input)
        depression_indicators = nlp_processor.extract_depression_indicators(user_input)
        
        # Lấy phiên chat
        chat_session_data = get_or_create_chat_session(user_id)
        chat_session_data['history'].append({'role': 'user', 'parts': [user_input]})
        
        # Tạo context mở rộng cho AI
        enhanced_context = f"""
        Phân tích tâm trạng hiện tại:
        - Điểm cảm xúc: {sentiment_analysis['score']:.2f} (-1 đến 1)
        - Đánh giá: {sentiment_analysis['analysis']}
        - Dấu hiệu trầm cảm phát hiện: {len(depression_indicators)} dấu hiệu
        - Chi tiết: {', '.join(depression_indicators) if depression_indicators else 'Không có dấu hiệu rõ ràng'}
        
        Tin nhắn người dùng: {user_input}
        
        Hãy phản hồi dựa trên phân tích này và đưa ra lời khuyên phù hợp.
        """
        
        # Gửi tới Gemini
        try:
            chat_session = model.start_chat(history=chat_session_data['history'])
            response = chat_session.send_message(enhanced_context)
            bot_response = response.text
        except Exception as e:
            logger.error(f"Lỗi API Gemini: {e}")
            # Fallback response
            bot_response = "Tôi hiểu bạn đang cần được lắng nghe. Mặc dù có một chút trục trặc kỹ thuật, tôi vẫn muốn bạn biết rằng cảm xúc của bạn là hoàn toàn hợp lý và bạn không cô đơn trong điều này."
        
        # Cập nhật lịch sử
        chat_session_data['history'].append({'role': 'model', 'parts': [bot_response]})
        chat_session_data['mood_tracking'].append({
            'timestamp': datetime.now().isoformat(),
            'sentiment': sentiment_analysis['score'],
            'indicators': depression_indicators
        })
        
        # Lấy đề xuất hoạt động
        recommendations = recommender.recommend_activities(sentiment_analysis, depression_indicators)
        
        # Kiểm tra tình huống khẩn cấp
        emergency_detected = any('suicidal_thoughts' in ind for ind in depression_indicators) or sentiment_analysis['score'] < -0.8
        
        # Chuẩn bị response
        enhanced_response = {
            "reply": bot_response,
            "sentiment_analysis": sentiment_analysis,
            "depression_indicators": depression_indicators,
            "recommendations": recommendations,
            "emergency_detected": emergency_detected,
            "mood_trend": "improving" if len(chat_session_data['mood_tracking']) > 1 and 
                         chat_session_data['mood_tracking'][-1]['sentiment'] > chat_session_data['mood_tracking'][-2]['sentiment'] 
                         else "stable"
        }
        
        if emergency_detected:
            enhanced_response["emergency_resources"] = recommender.get_emergency_resources()
        
        # Lưu vào database
        save_chat_to_database(user_id, user_input, bot_response, sentiment_analysis, depression_indicators)
        update_user_tracking(user_id, sentiment_analysis, recommendations)
        
        # Giới hạn lịch sử
        if len(chat_session_data['history']) > 30:
            chat_session_data['history'] = [chat_session_data['history'][0]] + chat_session_data['history'][-30:]
        
        logger.info(f"Xử lý hoàn tất cho user {user_id}")
        return jsonify(enhanced_response)

    except Exception as e:
        logger.error(f"Lỗi trong enhanced_chat: {e}")
        logger.error(traceback.format_exc())
        return jsonify({"error": "Đã có lỗi xảy ra khi xử lý yêu cầu", "detail": str(e)}), 500

@app.route('/mood-tracking/<user_id>', methods=['GET'])
def get_mood_tracking(user_id):
    """Lấy lịch sử theo dõi tâm trạng"""
    try:
        if user_id in chat_sessions:
            mood_data = chat_sessions[user_id]['mood_tracking']
            # Chỉ lấy 7 ngày gần nhất
            recent_data = mood_data[-7*24:] if len(mood_data) > 7*24 else mood_data
            return jsonify({"mood_tracking": recent_data})
        else:
            return jsonify({"mood_tracking": []})
    except Exception as e:
        logger.error(f"Lỗi lấy mood tracking: {e}")
        return jsonify({"error": "Lỗi lấy dữ liệu theo dõi"}), 500

@app.route('/reset', methods=['POST'])
def reset_chat():
    try:
        data = request.get_json()
        user_id = data.get('user_id', 'default_user') if data else 'default_user'
        
        # Reset phiên chat
        if user_id in chat_sessions:
            del chat_sessions[user_id]
        
        # Tạo phiên mới
        get_or_create_chat_session(user_id)
        
        logger.info(f"Đã reset chat cho user {user_id}")
        return jsonify({"message": "Cuộc trò chuyện đã được làm mới. Chúng ta hãy bắt đầu lại từ đầu nhé!"})
    except Exception as e:
        logger.error(f"Lỗi reset chat: {e}")
        return jsonify({"error": "Lỗi khi reset chat", "detail": str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        "status": "ok", 
        "message": "Enhanced Depression Support AI đang hoạt động",
        "features": ["PhoBERT Integration", "Mood Tracking", "Personalized Recommendations", "Emergency Detection"]
    }), 200

@app.route('/dashboard/<user_id>')
def user_dashboard(user_id):
    """Dashboard cho người dùng xem thống kê cá nhân"""
    try:
        conn = sqlite3.connect('depression_support.db')
        cursor = conn.cursor()
        
        # Lấy dữ liệu 30 ngày gần nhất
        thirty_days_ago = datetime.now() - timedelta(days=30)
        cursor.execute('''
            SELECT * FROM chat_history 
            WHERE user_id = ? AND timestamp > ?
            ORDER BY timestamp DESC
        ''', (user_id, thirty_days_ago))
        
        chat_history = cursor.fetchall()
        
        # Thống kê cơ bản
        if chat_history:
            avg_sentiment = sum(row[4] for row in chat_history) / len(chat_history)
            chat_count = len(chat_history)
            
            # Xu hướng cải thiện
            recent_chats = chat_history[:5]
            old_chats = chat_history[-5:] if len(chat_history) > 5 else []
            
            trend = "stable"
            if recent_chats and old_chats:
                recent_avg = sum(row[4] for row in recent_chats) / len(recent_chats)
                old_avg = sum(row[4] for row in old_chats) / len(old_chats)
                if recent_avg > old_avg + 0.1:
                    trend = "improving"
                elif recent_avg < old_avg - 0.1:
                    trend = "concerning"
        else:
            avg_sentiment = 0
            chat_count = 0
            trend = "no_data"
        
        conn.close()
        
        dashboard_data = {
            "user_id": user_id,
            "chat_count": chat_count,
            "avg_sentiment": round(avg_sentiment, 2),
            "trend": trend,
            "last_30_days_data": len(chat_history)
        }
        
        return jsonify(dashboard_data)
    except Exception as e:
        logger.error(f"Lỗi tạo dashboard: {e}")
        return jsonify({"error": "Lỗi tạo dashboard"}), 500

if __name__ == '__main__':
    logger.info("Khởi động Enhanced Depression Support AI Service...")
    app.run(host='0.0.0.0', port=5001, debug=True)  # Chạy Flask server