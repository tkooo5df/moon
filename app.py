
import os
import logging
import asyncio
import base64
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
import google.generativeai as genai
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
)
from motor.motor_asyncio import AsyncIOMotorClient
from textblob import TextBlob
import json

# تهيئة المتغيرات الأساسية
GEMINI_API = "AIzaSyCmQxBZrSjx284cGBMoMo9DPkidbyjAvsA"
TELEGRAM_TOKEN = "8074405702:AAFbqNtMb_atBEb4BMiJnwYD0JkQsFnavNg"
MONGO_URL = "mongodb+srv://aminekerkarr:S6AzL3AE1buIhBIq@cluster0.u9ckn.mongodb.net/?retryWrites=true&w=majority"

# تهيئة Gemini API
genai.configure(api_key=GEMINI_API)

class Config:
    TELEGRAM_TOKEN = TELEGRAM_TOKEN
    GEMINI_API = GEMINI_API
    MONGO_URL = MONGO_URL
    ADMIN_IDS = [6793977662]  # Your admin ID
    
    if not all([TELEGRAM_TOKEN, GEMINI_API, MONGO_URL]):
        raise ValueError("Missing required tokens")

class Database:
    def __init__(self, mongo_url: str):
        self.client = AsyncIOMotorClient(mongo_url)
        self.db = self.client['db1']
        self.users = self.db["users"]
        self.chats = self.db["chat_history"]
        self.files = self.db["file_metadata"]
    
    async def user_exists(self, chat_id: int) -> bool:
        user = await self.users.find_one({"chat_id": chat_id})
        return user is not None
    
    async def save_user(self, user_data: Dict[str, Any]) -> None:
        await self.users.insert_one(user_data)
    
    async def update_user(self, chat_id: int, update_data: Dict[str, Any]) -> None:
        await self.users.update_one(
            {"chat_id": chat_id},
            {"$set": update_data}
        )
    
    async def save_chat(self, chat_data: Dict[str, Any]) -> None:
        await self.chats.insert_one(chat_data)
    
    async def save_file(self, file_data: Dict[str, Any]) -> None:
        await self.files.insert_one(file_data)

class AIHandler:
    def __init__(self, api_key: str):
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel("gemini-1.5-pro")
        
        self.base_context = """
         تعليمات المساعد الذكي باللهجة الجزائرية:

        1. عند السؤال عن المطور/المبرمج:
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
    
    async def get_response(self, user_message: str) -> Optional[str]:
        max_retries = 3
        retry_delay = 20  # seconds
        
        for attempt in range(max_retries):
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
                return response.text
            
            except Exception as e:
                error_str = str(e).lower()
                if "quota" in error_str or "rate limit" in error_str or "429" in error_str:
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay)
                        continue
                    return None  # Return None for quota errors
                
                self.logger.error(f"Error in get_response: {str(e)}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                    continue
                return f"سمحلي خويا، كاين مشكل 😅"
    
    async def analyze_image(self, image_data: bytes, prompt: str = "وصف هذه الصورة باللهجة الجزائرية") -> Optional[str]:
        max_retries = 3
        retry_delay = 20  # seconds
        
        for attempt in range(max_retries):
            try:
                image_part = {
                    "mime_type": "image/jpeg",
                    "data": base64.b64encode(image_data).decode("utf-8")
                }
                
                response = await asyncio.to_thread(
                    self.model.generate_content,
                    [prompt, image_part]
                )
                return response.text
            
            except Exception as e:
                error_str = str(e).lower()
                if "quota" in error_str or "rate limit" in error_str or "429" in error_str:
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay)
                        continue
                    return None  # Return None for quota errors
                
                self.logger.error(f"Error in analyze_image: {str(e)}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                    continue
                return "ما قدرتش نحلل الصورة يا خويا 😅"

class TelegramBot:
    def __init__(self):
        self.db = Database(MONGO_URL)
        self.ai = AIHandler(GEMINI_API)
        self.logger = logging.getLogger(__name__)
        self.user_last_message = {}  # Store last message timestamp per user
        self.message_cooldown = 3  # Cooldown in seconds between messages
        self.warning_counts = {}  # Track warning counts per user
        self.max_warnings = 3  # Maximum warnings before temporary block
        self.block_duration = 300  # Block duration in seconds (5 minutes)
        self.blocked_users = {}  # Store blocked users and their unblock time

    def is_admin(self, chat_id: int) -> bool:
        return chat_id in Config.ADMIN_IDS
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = update.effective_chat.id
        user = update.effective_user
        
        if not await self.db.user_exists(chat_id):
            await self.db.save_user({
                "chat_id": chat_id,
                "first_name": user.first_name,
                "username": user.username,
                "phone_number": None,
                "registered_at": datetime.now(timezone.utc)
            })
            await self.request_phone_number(update)
        else:
            await update.message.reply_text("راك مسجل خويا! ��")
        
        if self.is_admin(chat_id):
            welcome_message = """
            أهلا بيك في بوتنا الذكي! 🎉

            نقدر نساعدك في بزاف حوايج:
            📊 /analytics - شوف الإحصائيات تاعك
            📈 /dashboard - شوف اللوحة تاع المعلومات
            🔍 /websearch - ابحث في الويب
            
            راني هنا باش نجاوبك على أي سؤال بطريقة مضحكة وجدية في نفس الوقت! 😊
            """
        else:
            welcome_message = """
            أهلا بيك في بوتنا الذكي! 🎉
            
            راني هنا باش نجاوبك على أي سؤال بطريقة مضحكة وجدية في نفس الوقت! 😊
            """
        await update.message.reply_text(welcome_message)
    
    async def request_phone_number(self, update: Update) -> None:
        keyboard = [[KeyboardButton("شارك رقم الهاتف تاعك 📱", request_contact=True)]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        
        await update.message.reply_text(
            "يا صاحبي، نحتاج رقم تيليفونك باش نتواصلو 📞\n"
            "اضغط على الزر لي تحت:",
            reply_markup=reply_markup
        )
    
    async def save_phone_number(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = update.effective_chat.id
        phone_number = update.message.contact.phone_number
        
        await self.db.update_user(chat_id, {"phone_number": phone_number})
        await update.message.reply_text("صحا! تسجل رقم الهاتف تاعك. 🎯")
    
    async def check_rate_limit(self, chat_id: int) -> tuple[bool, Optional[str]]:
        current_time = datetime.now(timezone.utc)
        
        # Check if user is blocked
        if chat_id in self.blocked_users:
            unblock_time = self.blocked_users[chat_id]
            if current_time < unblock_time:
                remaining = (unblock_time - current_time).seconds
                return False, f"راك مبلوكي لمدة {remaining} ثواني بسبب الإرسال المتكرر 🚫"
            else:
                del self.blocked_users[chat_id]
                if chat_id in self.warning_counts:
                    del self.warning_counts[chat_id]
        
        # Check cooldown
        if chat_id in self.user_last_message:
            time_since_last = (current_time - self.user_last_message[chat_id]).total_seconds()
            if time_since_last < self.message_cooldown:
                # Increment warning counter
                self.warning_counts[chat_id] = self.warning_counts.get(chat_id, 0) + 1
                
                # If max warnings reached, block user
                if self.warning_counts[chat_id] >= self.max_warnings:
                    block_until = current_time + timedelta(seconds=self.block_duration)
                    self.blocked_users[chat_id] = block_until
                    return False, f"تم حظرك لمدة {self.block_duration//60} دقائق بسبب الإرسال المتكرر 🚫"
                
                return False, f"استنى {self.message_cooldown} ثواني قبل ما ترسل مسج جديد ⏳ ({self.warning_counts[chat_id]}/{self.max_warnings} تحذيرات)"
        
        # Update last message time
        self.user_last_message[chat_id] = current_time
        return True, None

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = update.effective_chat.id
        user_text = update.message.text
        
        # Check rate limit
        can_proceed, warning_msg = await self.check_rate_limit(chat_id)
        if not can_proceed:
            if warning_msg:
                await update.message.reply_text(warning_msg)
            return
        
        try:
            # تحليل المشاعر
            sentiment = TextBlob(user_text).sentiment.polarity
            sentiment_label = (
                "إيجابي 😊" if sentiment > 0.2 else
                "سلبي 😔" if sentiment < -0.2 else
                "محايد 😐"
            )
            
            # الحصول على رد من الذكاء الاصطناعي
            ai_reply = await self.ai.get_response(user_text)
            
            # Only proceed if we got a response (not None)
            if ai_reply is not None:
                # حفظ المحادثة
                await self.db.save_chat({
                    "chat_id": chat_id,
                    "user_message": user_text,
                    "ai_response": ai_reply,
                    "sentiment": sentiment_label,
                    "timestamp": datetime.now(timezone.utc)
                })
                
                await update.message.reply_text(ai_reply)
            
        except Exception as e:
            self.logger.error(f"Error in handle_message: {str(e)}", exc_info=True)
            # Don't send error message to user

    async def handle_files(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = update.effective_chat.id
        message = update.message

        # Check rate limit for file uploads too
        can_proceed, warning_msg = await self.check_rate_limit(chat_id)
        if not can_proceed:
            if warning_msg:
                await update.message.reply_text(warning_msg)
            return
        
        try:
            if message.photo:
                file_id = message.photo[-1].file_id
                mime_type = "image/jpeg"
            elif message.document:
                file_id = message.document.file_id
                mime_type = message.document.mime_type or "application/octet-stream"
            else:
                return
            
            file = await context.bot.get_file(file_id)
            file_data = await file.download_as_bytearray()
            
            # تحليل الصورة
            description = await self.ai.analyze_image(file_data)
            
            # Only proceed if we got a response (not None)
            if description is not None:
                # حفظ معلومات الملف
                await self.db.save_file({
                    "chat_id": chat_id,
                    "file_id": file_id,
                    "description": description,
                    "timestamp": datetime.now(timezone.utc)
                })
                
                await update.message.reply_text(f"🖼️ شوف واش لقيت في الصورة:\n\n{description}")
            
        except Exception as e:
            self.logger.error(f"Error processing file: {str(e)}", exc_info=True)
            # Don't send error message to user

    async def admin_only(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        chat_id = update.effective_chat.id
        if not self.is_admin(chat_id):
            await update.message.reply_text("عذراً، هذا الأمر متاح للمشرفين فقط 🔒")
            return False
        return True

    async def analytics(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self.admin_only(update, context):
            return
        
        try:
            # استدعاء وظيفة التحليل من ملف analytics.py
            from analytics import fetch_analytics_summary, generate_dashboard
            
            # إرسال رسالة "جاري التحليل"
            processing_msg = await update.message.reply_text("راني نحلل المعطيات... ⏳")
            
            # جلب ملخص التحليلات
            summary = await fetch_analytics_summary(self.db.users, self.db.chats)
            await update.message.reply_text(summary)
            
            # إنشاء لوحة المعلومات
            dashboard_path = await generate_dashboard(self.db.users, self.db.chats)
            
            # إرسال الصورة
            with open(dashboard_path, 'rb') as photo:
                await update.message.reply_photo(photo)
            
            # حذف الملف بعد إرساله
            os.remove(dashboard_path)
            
            # حذف رسالة "جاري التحليل"
            await processing_msg.delete()
            
        except Exception as e:
            await update.message.reply_text(f"عندي مشكل في التحليل 😅: {str(e)}")
            self.logger.error(f"Error in analytics: {str(e)}", exc_info=True)

    async def dashboard(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self.admin_only(update, context):
            return
            
        try:
            # إرسال رسالة "جاري التحميل"
            processing_msg = await update.message.reply_text("راني نجهز لوحة المعلومات... ⌛")
            
            # جمع الإحصائيات
            users_count = await self.db.users.count_documents({})
            chats_count = await self.db.chats.count_documents({})
            files_count = await self.db.files.count_documents({})
            
            # حساب نشاط آخر 24 ساعة
            yesterday = datetime.now(timezone.utc) - timedelta(days=1)
            recent_chats = await self.db.chats.count_documents({"timestamp": {"$gte": yesterday}})
            
            dashboard_text = f"""
📊 **لوحة المعلومات**

👥 **إحصائيات عامة:**
• عدد المستخدمين: {users_count}
• مجموع المحادثات: {chats_count}
• عدد الملفات: {files_count}

📈 **النشاط:**
• المحادثات في 24 ساعة: {recent_chats}

⚡ **حالة النظام:**
• البوت نشط ✅
• قاعدة البيانات متصلة ✅
• API Gemini متصل ✅

🕐 آخر تحديث: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC
            """
            
            # حذف رسالة "جاري التحميل"
            await processing_msg.delete()
            
            # إرسال لوحة المعلومات
            await update.message.reply_text(dashboard_text, parse_mode='Markdown')
            
        except Exception as e:
            await update.message.reply_text(f"عندي مشكل في عرض لوحة المعلومات 😅: {str(e)}")
            self.logger.error(f"Error in dashboard: {str(e)}", exc_info=True)

    async def websearch(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self.admin_only(update, context):
            return
        # Add your websearch logic here

    def run(self):
        try:
            application = Application.builder().token(TELEGRAM_TOKEN).build()
            
            application.add_handler(CommandHandler("start", self.start))
            application.add_handler(CommandHandler("analytics", self.analytics))
            application.add_handler(CommandHandler("dashboard", self.dashboard))
            application.add_handler(CommandHandler("websearch", self.websearch))
            application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
            application.add_handler(MessageHandler(filters.PHOTO, self.handle_files))
            
            print("البوت راه يخدم بكل نشاط! 🚀")
            application.run_polling(allowed_updates=Update.ALL_TYPES)
            
        except Exception as e:
            print(f"يا خسارة! كاين مشكل في تشغيل البوت 😢: {str(e)}")
            raise

def main():
    # إعداد التسجيل
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    
    # تشغيل البوت
    bot = TelegramBot()
    try:
        bot.run()
    except KeyboardInterrupt:
        print("\nتم إيقاف البوت بنجاح! 👋")
    except Exception as e:
        print(f"خطأ غير متوقع: {str(e)}")

if __name__ == "__main__":
    main()
