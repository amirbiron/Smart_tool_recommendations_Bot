# 🤖 בוט המלצות כלים חכמים - מדריך הפעלה ופריסה

מדריך זה ילווה אותך צעד אחר צעד בהפעלת בוט הטלגרם שלך על שרתי Render.

---

### שלב 1: השגת מפתחות API ו-ID

הבוט זקוק למספר מפתחות סודיים כדי לפעול. נגדיר אותם כמשתני סביבה ב-Render.

1.  **Telegram Bot Token**:
    * פנה ל-`@BotFather` בטלגרם והשתמש בפקודה `/newbot`.
    * שמור את הטוקן שתקבל.

2.  **Groq API Key**:
    * גש לאתר [Groq Console](https://console.groq.com/keys) וצור מפתח API.
    * שמור את המפתח.

3.  **Admin Telegram ID**:
    * פנה בטלגרם לבוט `@userinfobot` והוא יציג לך את ה-ID שלך. שמור אותו.

### שלב 1.5: הגדרת בסיס נתונים (אופציונלי, לסטטיסטיקות)

1.  **צור חשבון חינמי** ב-[MongoDB Atlas](https://www.mongodb.com/cloud/atlas/register).
2.  **צור קלאסטר (Cluster)** חינמי.
3.  **צור משתמש לבסיס הנתונים** ושמור את פרטיו.
4.  **אפשר גישה מכל מקום** (`Allow Access from Anywhere`).
5.  **העתק את כתובת ההתחברות (Connection String)** והחלף בה את שם המשתמש והסיסמה.

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

### שלב 4: הגדרת Keep-Alive

1.  העתק את כתובת ה-URL של השירות שלך מ-Render.
2.  ב-[UptimeRobot](https://uptimerobot.com/), צור **New Monitor** מסוג `HTTP(s)`.
3.  הדבק את ה-URL והגדר את **Monitoring Interval** ל-`Every 5 minutes`.

---

### 🌐 שירותים חיצוניים

הבוט מסתמך על מספר שירותים חיצוניים כדי לפעול:
* **[Render](https://render.com/):** פלטפורמת הענן שמריצה את הבוט 24/7.
* **[Groq](https://groq.com/):** מספקת את מודל השפה המהיר להבנת בקשות המשתמשים.
* **[MongoDB Atlas](https://www.mongodb.com/cloud/atlas):** בסיס הנתונים שבו נשמרים פרטי המשתמשים לסטטיסטיקה.
* **[UptimeRobot](https://uptimerobot.com/):** שירות הניטור ששומר על הבוט "ער" ומונע ממנו להירדם.
