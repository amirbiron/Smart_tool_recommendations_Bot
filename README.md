# 🤖 בוט המלצות כלים חכמים - מדריך הפעלה ופריסה

מדריך זה ילווה אותך צעד אחר צעד בהפעלת בוט הטלגרם שלך על שרתי Render.

---

## 📋 שלבי התקנה

### שלב 1: השגת מפתחות API ו-ID

הבוט זקוק למספר מפתחות סודיים כדי לפעול. נגדיר אותם כמשתני סביבה ב-Render.

1.  **Telegram Bot Token**:
    * פנה ל-`@BotFather` בטלגרם והשתמש בפקודה `/newbot`.
    * שמור את הטוקן שתקבל.

2.  **Groq API Key**:
    * גש לאתר [Groq Console](https://console.groq.com/keys) וצור מפתח API.
    * שמור את המפתח.

3.  **Admin Telegram ID**:
    * כדי להשתמש בפקודת האדמין `/stats`, הבוט צריך לדעת מה ה-ID שלך.
    * פנה בטלגרם לבוט `@userinfobot` והוא יציג לך את ה-ID שלך. שמור אותו.

### שלב 1.5: הגדרת MongoDB (אופציונלי, לסטטיסטיקות)

1.  **צור חשבון חינמי** ב-[MongoDB Atlas](https://www.mongodb.com/cloud/atlas/register).
2.  **צור קלאסטר (Cluster)** חינמי. בחר בספק ענן ואזור הקרובים אליך (למשל, AWS בפרנקפורט).
3.  **צור משתמש לבסיס הנתונים**:
    * בתפריט הצד, לך ל-`Database Access`.
    * צור משתמש חדש עם שם וסיסמה. שמור את הפרטים.
4.  **אפשר גישה מכל מקום**:
    * בתפריט הצד, לך ל-`Network Access`.
    * לחץ על `Add IP Address` ובחר `Allow Access from Anywhere`. זה הכי פשוט עבור Render.
5.  **קבל את כתובת ההתחברות (Connection String)**:
    * חזור למסך הראשי (Databases), לחץ על `Connect` ליד הקלאסטר שלך.
    * בחר `Drivers`.
    * העתק את ה-**Connection String** שמופיעה. היא תיראה דומה לזה: `mongodb+srv://<username>:<password>@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority`
    * **חשוב:** החלף את `<username>` ו-`<password>` בפרטי המשתמש שיצרת בשלב 3.

### שלב 2: העלאת הפרויקט ל-GitHub

1.  צור מאגר (repository) חדש בחשבון ה-GitHub שלך.
2.  העלה את כל קבצי הפרויקט למאגר זה.

### שלב 3: הגדרת הפרויקט ב-Render

1.  לחץ על **New +** ובחר **Blueprint**. חבר את מאגר ה-GitHub שלך.
2.  Render יזהה את קובץ `render.yaml`. תן שם לשירות.
3.  עבור ללשונית **Environment**.
4.  תחת **Secret Files**, צור קובץ בשם `.env` עם התוכן הבא (החלף בערכים שאספת):

    ```
    BOT_TOKEN=הטוקן_של_הבוט_שלך_מטלגרם
    GROQ_API_KEY=מפתח_ה-API_שלך_מ-Groq
    MONGO_URI=כתובת_ההתחברות_שלך_מ-MongoDB_Atlas
    ADMIN_ID=ה-ID_שלך_מטלגרם
    ```

5.  לחץ על **Create New Web Service**.

### שלב 4: הגדרת Keep-Alive עם UptimeRobot

1.  העתק את כתובת ה-URL של השירות שלך מ-Render (`https://your-service-name.onrender.com`).
2.  ב-**UptimeRobot**, צור **New Monitor** מסוג `HTTP(s)`.
3.  הדבק את ה-URL והגדר את **Monitoring Interval** ל-`Every 5 minutes`.

**זהו! הבוט שלך באוויר, עם יכולות משופרות!** 🎉
