from flask import Flask, request, jsonify
import requests
import json
import time
import re
from concurrent.futures import ThreadPoolExecutor
import os
import pickle
from datetime import datetime, timedelta
import google.generativeai as genai
import asyncio
from typing import Optional

app = Flask(__name__)

# توكن الوصول والرابط من facebook.py
FACEBOOK_PAGE_ACCESS_TOKEN = 'EAAoLY619jZAMBO4YUFGXGmfCMSsmZBfgjZBkNStozN5eSyBT1UZCJhinAPASssGQlHuUjCaV7nAThnhOCjxVGcxoh1aa67zMjupx2ThFcXYQpuvxVagOB5o6atJvdf6FLtghzJUflL2JjPjkqus4vqbZB1MipOZCpVmM3yyetQUFjKNbIl6KZBStdovZB2xemvVHswZDZD'
FACEBOOK_GRAPH_API_URL = 'https://graph.facebook.com/v11.0/me/messages'
MAX_MESSAGE_LENGTH = 2000

# متغيرات النظام
admin = 6793977662  # معرف المسؤول
total_users = {}  # تغيير من set الى dictionary
user_context = {}
processed_message_ids = set()
BOT_START_TIME = None  # وقت بدء تشغيل البوت

# ملفات حفظ البيانات
PROCESSED_IDS_FILE = 'processed_message_ids.pkl'
TOTAL_USERS_FILE = 'total_users.pkl'

# الحد الأقصى للرسائل القديمة لاستردادها عند التشغيل
MAX_HISTORY_MESSAGES = 5
# فترة زمنية لاسترداد الرسائل القديمة (بالساعات)
HISTORY_TIME_WINDOW = 24  # ساعة 

# إضافة استيراد مكتبة Gemini
import google.generativeai as genai

class AIHandler:
    def __init__(self, api_key: str):
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel("gemini-pro")
        self.vision_model = genai.GenerativeModel('gemini-pro-vision')
        self.retry_count = 0
        self.max_retries = 3
        self.retry_delay = 2  # ثواني
        
        self.base_context = """
        تعليمات المساعد الذكي باللهجة الجزائرية:

        1. عند السؤال فقط عن المطور/المبرمج:
           - "طورني أمين من الجزائر 🇩🇿"
           - "تقدر تتواصل معاه على الانستا: amine.kr7"
           - لا تذكر أي معلومات تقنية أو نماذج مستخدمة.
           - اكتفِ بالقول إنك مصمم من أمين 

        2. أسلوب التحدث:
           - استخدم أسلوبًا محايدًا تمامًا.
           - تجنب أي كلمات تشير للجنس.
           - لا تستخدم كلمات مثل (خويا، صديقي، عزيزي).
           - لا تسأل عن الحال في بداية كل محادثة مثل "وشراك؟".
           - ركّز على الإجابة المباشرة للسؤال.
           - كن محترمًا ومهنيًا.
           -في حال ما تم سؤالك عن امر علمي او دراسي تجنب الضحك والاسلوب الهين 

        3. التعابير المسموحة والمستخدمة:
        
           ✅ **الموافقة والرفض:**
              - صح / واه / إي = نعم
              - خاطي / لالا / ماشي = لا
              - عندك الصح = أنت على حق
              - راك غالط = أنت مخطئ
        
           ✅ **التعبير عن الحال والسؤال عنه:**
              - واش راك؟ / كاش راك؟ = كيف حالك؟
              - لاباس؟ = هل أنت بخير؟
              - الحمد لله، لباس = بخير، الحمد لله
              - ماشي مليح = لست بخير
              - نتمشى شوية = أتحسن قليلًا
              - راك نورمال؟ = هل أنت بخير؟
              - راك مقلق؟ = هل أنت منزعج؟
              - ماعلاباليش = لا أعلم
        
           ✅ **التعبير عن الكمية:**
              - شوية = قليل
              - بزاف = كثير
              - قد قد = معتدل
              - نص نص = متوسط

           ✅ **التعبير عن الوقت:**
              - دروك / دكا / دوكا = الآن
              - من بكري = منذ وقت طويل
              - مبعد / من بعد = لاحقًا
              - طواك الوقت = فات الأوان
              - نهار كامل = طوال اليوم
              - عشية / لعشية = المساء
              - صبّحنا = أصبحنا
              - في الغدوا = في الصباح
        
           ✅ **التعبير عن الأماكن والاتجاهات:**
              - لهيه = هناك
              - لهنا = هنا
              - الجهة هذي = هذا الاتجاه
              - قدّام = أمام
              - اللّور = الخلف
              - عوجة = منعطف

           ✅ **التعبير عن العواطف والمشاعر:**
              - فرحان / متهني = سعيد
              - زكارة / قهر = غضب أو قهر
              - مقلق / معصب = غاضب
              - محروق قلبي = قلبي محروق (حزين)
              - راسي راهي تسوطي = أشعر بصداع شديد
              - نتمحن بزاف = أعاني كثيرًا
              - شاد روحي = أحاول ضبط نفسي

           ✅ **التعبير عن الطلبات والتوجيهات:**
              - جيبلي... = أحضر لي...
              - عطيه لي = أعطني إياه
              - روح تجيب... = اذهب وأحضر...
              - بركّح روحك = استرخي
              - طفي الضو = أطفئ النور
              - خليها عليك = لا تهتم بها
              - ماكاش مشكل = لا يوجد مشكلة

           ✅ **التعبير عن الصفات والأحوال:**
              - مليح / ملاح = جيد
              - ماشي مليح = ليس جيد
              - ماشي نورمال = غير طبيعي
              - خاطيه لحليب = لا يفهم بسرعة / غبي
              - زاهي = سعيد
              - خامج = وسخ أو سيئ
              - عفسة مليحة = شيء جيد

           ✅ **التعبير عن العمل والنشاط:**
              - نخدم = أعمل
              - نخمّم = أفكر
              - ما عنديش الجهد = ليس لدي طاقة
              - نتهلّى فيك = سأعتني بك
              - نسرق شوية ريحة = سأرتاح قليلًا

           ✅ **التعبير عن الأحداث والمواقف:**
              - واش صرا؟ = ماذا حدث؟
              - كي العادة = كالمعتاد
              - شحال صرا لها؟ = منذ متى حدث ذلك؟
              - ماشي شغلي = ليس من شأني
              - ضرك نوريه = سأريه الآن

           ✅ **التعبير عن الرغبات والتفضيلات:**
              - واش تحوس؟ = ماذا تريد؟
              - نحب هذا = أحب هذا
              - ما يعجبنيش = لا يعجبني
              - علاه لا؟ = لماذا لا؟
              - بغيت ناكل = أريد أن آكل

           ✅ **عبارات جزائرية مشهورة:**
              - خويا / خيتي = أخي / أختي (للمخاطبة الودية)
              - يخي حالة! = يا لها من فوضى!
              - على حساب = حسب الظروف
              - ربي يعيشك = شكرًا لك (بمعنى الله يطيل عمرك)
              - الله غالب = هذا هو القدر
              - ما درنا والو = لم نفعل شيئًا
              - زعما زعما = كأنه، أو بمعنى تهكمي "يعني فعلًا؟!"
              - هاذي تاع الصح = هذا حقيقي تمامًا
              - راني معاك = أنا معك
              - غير هكا = فقط هكذا

        4. استخدم دائمًا:
           - اللهجة الجزائرية الدارجة.
           - التعابير الجزائرية المحايدة.
           - الإيموجي المناسبة 😊.
        """
    
    async def analyze_image(self, image_data: bytes, prompt: str = None) -> Optional[str]:
        if prompt is None:
            prompt = "وصف هذه الصورة باللهجة الجزائرية"
            
        while self.retry_count < self.max_retries:
            try:
                image_parts = [
                    {
                        "mime_type": "image/jpeg",
                        "data": image_data
                    }
                ]
                prompt_parts = [prompt] + image_parts
                
                response = await asyncio.to_thread(
                    self.vision_model.generate_content,
                    prompt_parts
                )
                self.retry_count = 0
                return response.text
                
            except Exception as e:
                self.retry_count += 1
                if self.retry_count < self.max_retries:
                    await asyncio.sleep(self.retry_delay * self.retry_count)
                    continue
                print(f"Error in analyze_image after {self.max_retries} retries: {str(e)}")
                return None
        
        self.retry_count = 0
        return None

    async def get_response(self, user_message: str) -> Optional[str]:
        while self.retry_count < self.max_retries:
            try:
                prompt = f"""
                {self.base_context}
                رسالة المستخدم: {user_message}
                قم بالرد باللهجة الجزائرية مع مراعاة التعليمات أعلاه.
                """
                
                response = await asyncio.to_thread(
                    self.model.generate_content,
                    prompt
                )
                self.retry_count = 0
                return response.text
                
            except Exception as e:
                self.retry_count += 1
                if self.retry_count < self.max_retries:
                    await asyncio.sleep(self.retry_delay * self.retry_count)
                    continue
                print(f"Error in get_response after {self.max_retries} retries: {str(e)}")
                return None
        
        self.retry_count = 0
        return None

# تهيئة Gemini API
GEMINI_API = os.getenv("GEMINI_API", "AIzaSyC8swpbv_LJPo5V3HpF5j94QsAfI633mIs")
ai_handler = AIHandler(GEMINI_API)

# تحميل البيانات المحفوظة
def load_saved_data():
    """
    تحميل البيانات المحفوظة من الملفات
    """
    global processed_message_ids, user_context, total_users
    
    try:
        if os.path.exists(PROCESSED_IDS_FILE):
            with open(PROCESSED_IDS_FILE, 'rb') as f:
                processed_message_ids = pickle.load(f)
            print(f"تم تحميل {len(processed_message_ids)} معرف رسالة")
            
        if os.path.exists(TOTAL_USERS_FILE):
            with open(TOTAL_USERS_FILE, 'rb') as f:
                total_users = pickle.load(f)
                if isinstance(total_users, set):  # تحويل من set الى dictionary إذا كان قديماً
                    new_total_users = {}
                    for user_id in total_users:
                        new_total_users[user_id] = {
                            'message_count': 0,
                            'first_interaction': datetime.now(),
                            'last_interaction': datetime.now()
                        }
                    total_users = new_total_users
            print(f"تم تحميل معلومات {len(total_users)} مستخدم")
            
    except Exception as e:
        print(f"خطأ في تحميل البيانات: {e}")
        # تهيئة القيم الافتراضية في حالة الخطأ
        processed_message_ids = set()
        total_users = {}

# حفظ البيانات دوريًا
def save_data():
    try:
        with open(PROCESSED_IDS_FILE, 'wb') as f:
            pickle.dump(processed_message_ids, f)
        with open(TOTAL_USERS_FILE, 'wb') as f:
            pickle.dump(total_users, f)
        
        print(f"تم حفظ البيانات: {len(processed_message_ids)} رسالة، {len(total_users)} مستخدم")
    except Exception as e:
        print(f"خطأ في حفظ البيانات: {e}")

def validate_message(message_text):
    """
    التحقق من صحة الرسالة قبل إرسالها
    """
    if not message_text or not isinstance(message_text, str):
        return False
    
    # التحقق من الرسائل المكررة مثل "هههههههه"
    if re.match(r'^(.)\1{10,}$', message_text):
        return False
    
    # التحقق من الأحرف المنقطعة أو غير المفهومة
    if len(message_text.strip()) < 3:
        return False
    
    # التحقق من وجود نص عربي حقيقي في الرسالة
    arabic_text_pattern = re.compile(r'[\u0600-\u06FF\s]{3,}')
    if not arabic_text_pattern.search(message_text):
        return False
    
    return True

def send_facebook_message(recipient_id, message_text, quick_replies=None):
    """
    إرسال رسالة إلى مستخدم فيسبوك مع التحقق من صحتها أولاً
    """
    if not validate_message(message_text):
        if recipient_id != admin:
            notify_admin_of_error(recipient_id, "رسالة غير صالحة", 
                                f"حاول البوت إرسال: {message_text[:100]}...")
            message_text = "سمحلي خويا/ختي، كاين مشكل تقني، راني نحاول نصلحه 🙏"
    
    url = FACEBOOK_GRAPH_API_URL
    params = {
        "access_token": FACEBOOK_PAGE_ACCESS_TOKEN
    }
    headers = {
        "Content-Type": "application/json"
    }
    
    # التحقق من طول الرسالة
    if len(message_text) > MAX_MESSAGE_LENGTH:
        message_text = message_text[:MAX_MESSAGE_LENGTH-100] + "..."
    
    data = {
        "recipient": {
            "id": str(recipient_id)  # تحويل المعرف إلى نص
        },
        "message": {
            "text": message_text
        }
    }
    
    if quick_replies:
        data["message"]["quick_replies"] = quick_replies

    try:
        response = requests.post(url, params=params, headers=headers, json=data)  # استخدام json بدل data
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as err:
        print(f"Error sending message: {err}")
        if recipient_id == admin:
            print(f"Failed to send message to admin. Error: {err}")
        return False

def notify_admin_of_error(user_id, error_type, error_details):
    """إرسال إشعار الخطأ إلى المسؤول"""
    message = f"🚨 كاين مشكل في البوت:\nUser: {user_id}\nنوع المشكل: {error_type}\nتفاصيل: {error_details}"
    send_facebook_message(admin, message)

# إضافة متغيرات للتحكم في معدل الرسائل
user_message_timestamps = {}  # تخزين توقيت آخر رسالة لكل مستخدم
user_messages_count = {}  # عدد رسائل المستخدم في الدقيقة الأخيرة
user_warnings = {}  # عدد التحذيرات لكل مستخدم
blocked_users = {}  # المستخدمين المحظورين ووقت انتهاء الحظر

# ثوابت للتحكم في معدل الرسائل
MESSAGE_COOLDOWN = 3  # الوقت المطلوب بين الرسائل (بالثواني)
MAX_MESSAGES_PER_MINUTE = 5  # الحد الأقصى للرسائل في الدقيقة
MAX_WARNINGS = 2  # عدد التحذيرات قبل الحظر
BLOCK_DURATION = 300  # مدة الحظر (5 دقائق)

def check_rate_limit(sender_id: str) -> tuple[bool, bool]:
    """
    التحقق من معدل إرسال الرسائل والتحذيرات والحظر
    يعيد (يمكن_الإرسال, تم_الحظر_للتو)
    """
    current_time = datetime.now()

    # التحقق من الحظر
    if sender_id in blocked_users:
        if current_time < blocked_users[sender_id]:
            print(f"المستخدم {sender_id} محظور")
            return False, False
        else:
            # إزالة الحظر والتحذيرات
            del blocked_users[sender_id]
            if sender_id in user_warnings:
                del user_warnings[sender_id]
            if sender_id in user_messages_count:
                del user_messages_count[sender_id]

    # تحديث عدد الرسائل في الدقيقة
    if sender_id not in user_messages_count:
        user_messages_count[sender_id] = {'count': 1, 'reset_time': current_time + timedelta(minutes=1)}
    else:
        if current_time > user_messages_count[sender_id]['reset_time']:
            # إعادة تعيين العداد بعد مرور دقيقة
            user_messages_count[sender_id] = {'count': 1, 'reset_time': current_time + timedelta(minutes=1)}
        else:
            # زيادة عدد الرسائل
            user_messages_count[sender_id]['count'] += 1
            
            # التحقق من تجاوز الحد الأقصى للرسائل
            if user_messages_count[sender_id]['count'] > MAX_MESSAGES_PER_MINUTE:
                user_warnings[sender_id] = user_warnings.get(sender_id, 0) + 1
                if user_warnings[sender_id] >= MAX_WARNINGS:
                    blocked_users[sender_id] = current_time + timedelta(seconds=BLOCK_DURATION)
                    print(f"تم حظر المستخدم {sender_id} لمدة {BLOCK_DURATION//60} دقائق")
                    return False, True
                return False, False

    # التحقق من الوقت بين الرسائل
    if sender_id in user_message_timestamps:
        time_since_last = (current_time - user_message_timestamps[sender_id]).total_seconds()
        if time_since_last < MESSAGE_COOLDOWN:
            user_warnings[sender_id] = user_warnings.get(sender_id, 0) + 1
            if user_warnings[sender_id] >= MAX_WARNINGS:
                blocked_users[sender_id] = current_time + timedelta(seconds=BLOCK_DURATION)
                print(f"تم حظر المستخدم {sender_id} لمدة {BLOCK_DURATION//60} دقائق")
                return False, True
            return False, False

    # تحديث وقت آخر رسالة
    user_message_timestamps[sender_id] = current_time
    return True, False

def handle_facebook_message(sender_id, message_text, message_id, created_time=None, is_historical=False, image_data=None):
    """
    معالجة رسالة فيسبوك واردة
    """
    if message_id in processed_message_ids:
        return
    
    processed_message_ids.add(message_id)
    
    # التحقق من معدل الرسائل
    can_proceed, just_blocked = check_rate_limit(sender_id)
    if not can_proceed:
        if just_blocked:
            # إرسال رسالة للمستخدم عند حظره
            block_message = f"عذراً، تم حظرك مؤقتاً لمدة {BLOCK_DURATION//60} دقائق بسبب إرسال الكثير من الرسائل في وقت قصير 🚫\nالرجاء المحاولة لاحقاً."
            send_facebook_message(sender_id, block_message)
        return

    # تحديث إحصائيات المستخدم
    if sender_id not in total_users:
        total_users[sender_id] = {
            'message_count': 0,
            'first_interaction': datetime.now(),
            'last_interaction': datetime.now()
        }
    
    total_users[sender_id]['message_count'] += 1
    total_users[sender_id]['last_interaction'] = datetime.now()
    
    # إنشاء سياق جديد إذا لم يكن موجوداً
    if sender_id not in user_context:
        user_context[sender_id] = []

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        if image_data:
            print(f"معالجة صورة من المستخدم {sender_id}")
            response = loop.run_until_complete(ai_handler.analyze_image(image_data))
        else:
            print(f"معالجة رسالة نصية من المستخدم {sender_id}")
            response = loop.run_until_complete(ai_handler.get_response(message_text))
            
        loop.close()
        
        # فقط إرسال الرد إذا كان صالحاً
        if response and validate_message(response):
            success = send_facebook_message(sender_id, response)
            if not success:
                print(f"فشل في إرسال الرسالة للمستخدم {sender_id}")
        
        save_data()
        
    except Exception as e:
        print(f"خطأ في معالجة الرسالة: {str(e)}")

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    """
    معالجة طلبات الويب هوك
    """
    if request.method == 'GET':
        verify_token = request.args.get('hub.verify_token')
        if verify_token == 'your_verify_token':
            return request.args.get('hub.challenge')
        return 'Invalid verification token'
    
    data = request.get_json()
    
    try:
        if data['object'] == 'page':
            for entry in data['entry']:
                # استخراج الطابع الزمني من الإدخال
                entry_time = entry.get('time', 0)
                if isinstance(entry_time, str):
                    entry_time = int(float(entry_time))
                
                # تجاهل الرسائل القديمة
                if entry_time and entry_time < int(BOT_START_TIME.timestamp()):
                    print(f"تجاهل رسالة قديمة (وقت الرسالة: {datetime.fromtimestamp(entry_time)})")
                    continue
                
                for messaging_event in entry['messaging']:
                    sender_id = messaging_event['sender']['id']
                    
                    # معالجة الصور
                    if 'message' in messaging_event and 'attachments' in messaging_event['message']:
                        for attachment in messaging_event['message']['attachments']:
                            if attachment['type'] == 'image':
                                image_url = attachment['payload']['url']
                                try:
                                    # تحميل الصورة
                                    image_response = requests.get(image_url)
                                    if image_response.status_code == 200:
                                        image_data = image_response.content
                                        message_id = messaging_event['message'].get('mid')
                                        print(f"تم استلام صورة من المستخدم {sender_id}")
                                        handle_facebook_message(
                                            sender_id=sender_id,
                                            message_text="",
                                            message_id=message_id,
                                            image_data=image_data
                                        )
                                except Exception as e:
                                    print(f"خطأ في تحميل الصورة: {str(e)}")
                                    continue
                    
                    # معالجة الرسائل النصية
                    elif 'message' in messaging_event and 'text' in messaging_event['message']:
                        message_text = messaging_event['message']['text']
                        message_id = messaging_event['message']['mid']
                        print(f"تم استلام رسالة نصية من المستخدم {sender_id}: {message_text}")
                        handle_facebook_message(
                            sender_id=sender_id,
                            message_text=message_text,
                            message_id=message_id
                        )
    except Exception as e:
        print(f"خطأ في معالجة webhook: {str(e)}")
    
    return jsonify({'status': 'ok'})

def poll_facebook_messages():
    """
    دالة مراقبة الرسائل الجديدة
    """
    global bot_start_time
    bot_start_time = int(time.time())
    last_checked = bot_start_time
    consecutive_errors = 0
    max_consecutive_errors = 5
    
    # تحميل البيانات المحفوظة قبل البدء
    load_saved_data()
    
    # استرجاع عدد محدود من الرسائل التاريخية
    get_limited_history()
    
    # حلقة مراقبة الرسائل الجديدة
    while True:
        try:
            url = f"https://graph.facebook.com/v11.0/me/conversations?fields=messages.limit(5){{message,from,id,created_time}}&since={last_checked}&access_token={FACEBOOK_PAGE_ACCESS_TOKEN}"
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            conversations = data.get('data', [])

            for conversation in conversations:
                messages = conversation.get('messages', {}).get('data', [])
                for message in messages:
                    message_id = message.get('id')
                    
                    if not message.get('message') or message_id in processed_message_ids:
                        continue
                    
                    sender_id = message.get('from', {}).get('id')
                    message_text = message.get('message')
                    created_time = message.get('created_time')
                    
                    if sender_id and message_text and sender_id != 'PAGE_ID':
                        print(f"رسالة جديدة من {sender_id} 📨: {message_text}")
                        handle_facebook_message(
                            sender_id,
                            message_text,
                            message_id,
                            created_time
                        )
            
            consecutive_errors = 0

        except Exception as e:
            consecutive_errors += 1
            print(f"مشكل في قراءة الرسائل: {e}")
            
            if consecutive_errors >= max_consecutive_errors:
                notify_admin_of_error("SYSTEM", "مشاكل متتالية في القراءة", 
                                     f"فشل {consecutive_errors} مرات. آخر مشكل: {e}")
                consecutive_errors = 0
                time.sleep(30)
            else:
                time.sleep(5)

        last_checked = int(time.time())
        time.sleep(2)

def get_limited_history():
    """
    استرجاع عدد محدود من الرسائل التاريخية باستخدام نافذة زمنية محددة
    """
    try:
        time_window = int(time.time()) - (HISTORY_TIME_WINDOW * 3600)  # تحويل الساعات إلى ثوانٍ
        url = f"https://graph.facebook.com/v11.0/me/conversations?fields=messages.limit(50){{message,from,id,created_time}}&access_token={FACEBOOK_PAGE_ACCESS_TOKEN}"
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        conversations = data.get('data', [])

        # فرز المستخدمين والعد لكل منهم
        user_message_counts = {}

        for conversation in conversations:
            messages = conversation.get('messages', {}).get('data', [])
            for message in messages:
                message_id = message.get('id')
                
                if not message.get('message') or message_id in processed_message_ids:
                    continue
                
                sender_id = message.get('from', {}).get('id')
                if sender_id == 'PAGE_ID' or not sender_id:
                    continue
                
                message_text = message.get('message')
                created_time_str = message.get('created_time')
                
                # تحويل التاريخ إلى كائن datetime
                if created_time_str:
                    message_time = datetime.strptime(created_time_str, "%Y-%m-%dT%H:%M:%S%z")
                    message_timestamp = message_time.timestamp()
                else:
                    continue  # تخطي الرسائل بدون تاريخ
                
                # تحقق مما إذا كانت الرسالة في النافذة الزمنية المطلوبة
                if message_timestamp < time_window:
                    continue
                
                # عد الرسائل لكل مستخدم
                if sender_id not in user_message_counts:
                    user_message_counts[sender_id] = []
                
                user_message_counts[sender_id].append({
                    'message_id': message_id,
                    'message_text': message_text,
                    'created_time': created_time_str,
                    'timestamp': message_timestamp
                })
        
        # معالجة الرسائل التاريخية المحدودة لكل مستخدم
        historical_message_count = 0
        for sender_id, messages in user_message_counts.items():
            # ترتيب رسائل المستخدم حسب التاريخ (الأحدث أولاً)
            sorted_messages = sorted(messages, key=lambda m: m['timestamp'], reverse=True)
            
            # أخذ الحد الأقصى فقط من الرسائل لكل مستخدم
            for idx, msg in enumerate(sorted_messages):
                if idx < MAX_HISTORY_MESSAGES:
                    print(f"استرداد رسالة تاريخية من {sender_id}: {msg['message_text']}")
                    handle_facebook_message(
                        sender_id,
                        msg['message_text'],
                        msg['message_id'],
                        msg['created_time'],
                        is_historical=True
                    )
                    historical_message_count += 1
                else:
                    break
        
        print(f"تم استرداد {historical_message_count} رسالة تاريخية محدودة.")
        
    except Exception as e:
        print(f"خطأ في استرداد الرسائل التاريخية: {e}")
        notify_admin_of_error("SYSTEM", "مشكل في استرداد الرسائل التاريخية", str(e))

def broadcast_message(message_text):
    """
    إرسال رسالة جماعية لجميع المستخدمين
    """
    if not validate_message(message_text):
        send_facebook_message(admin, "❌ الرسالة غير صالحة للإرسال الجماعي. الرجاء مراجعة محتوى الرسالة.")
        return
    
    sent_count = 0
    failed_users = []

    for user_id in total_users:
        try:
            if send_facebook_message(user_id, message_text):
                sent_count += 1
            else:
                failed_users.append(user_id)
        except Exception:
            failed_users.append(user_id)

    status_message = (
        f"صافي راهي وصلات الرسالة لـ {sent_count} مستخدم 🎯\n"
        f"ما وصلاتش لـ {len(failed_users)} مستخدم ❌"
    )
    send_facebook_message(admin, status_message)

    if failed_users:
        send_facebook_message(admin, f"المستخدمين لي ما وصلاتلهمش: {', '.join(map(str, failed_users))}")

@app.route('/broadcast', methods=['POST'])
def start_broadcast():
    """
    معالجة طلب إرسال رسالة جماعية
    """
    data = request.json
    message = data.get('message')
    if not message:
        return jsonify({'status': 'error', 'message': 'ما كاين حتى رسالة'})
    
    broadcast_message(message)
    return jsonify({'status': 'ok'})

# تحديث توكن الفيسبوك وإضافة التحقق من صلاحيته
def verify_facebook_token():
    try:
        url = f"https://graph.facebook.com/v11.0/me?access_token={FACEBOOK_PAGE_ACCESS_TOKEN}"
        response = requests.get(url)
        if response.status_code != 200:
            notify_admin_of_error("SYSTEM", "توكن فيسبوك غير صالح", 
                                "الرجاء تحديث التوكن في ملف .env")
            return False
        return True
    except Exception as e:
        print(f"Error verifying token: {e}")
        return False

# تحديث دالة التشغيل الرئيسية
if __name__ == '__main__':
    # التحقق من صلاحية توكن فيسبوك عند بدء التشغيل
    if not verify_facebook_token():
        print("توكن فيسبوك غير صالح! الرجاء التحقق من التوكن وإعادة التشغيل.")
        exit(1)
    
    load_saved_data()
    BOT_START_TIME = datetime.now()  # تعيين وقت بدء تشغيل البوت
    print(f"تم بدء تشغيل البوت في: {BOT_START_TIME}")
    
    with ThreadPoolExecutor() as executor:
        executor.submit(poll_facebook_messages)
        app.run(port=5000, debug=False)