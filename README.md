# 🤖 בוט המלצות כלים חכמים - מדריך הפעלה ופריסה

מדריך זה ילווה אותך צעד אחר צעד בהפעלת בוט הטלגרם שלך על שרתי Render, כולל שילוב חיפוש חי ועדכני באינטרנט.

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

### שלב 2: הגדרת שירותי Google Cloud (לחיפוש חי)

כדי לאפשר חיפוש חי ועדכני, נשתמש ב-API של גוגל.

1.  **השג מפתח API:**
    * לך ל-[Google Cloud Console](https://console.cloud.google.com/).
    * צור פרויקט חדש.
    * בתפריט הניווט, לך ל-`APIs & Services` > `Credentials`.
    * לחץ על `+ CREATE CREDENTIALS` ובחר `API key`. העתק את המפתח ושמור אותו.
    * לך ל-`APIs & Services` > `Library`, חפש את `Custom Search API` והפעל אותו (`Enable`).

2.  **צור מנוע חיפוש מותאם אישית:**
    * לך ל-[Programmable Search Engine control panel](https://programmablesearchengine.google.com/controlpanel/all).
    * לחץ על `Add`.
    * ב-`What to search?`, בחר באפשרות **Search the entire web**.
    * תן שם למנוע החיפוש שלך ולחץ `Create`.
    * לאחר שנוצר, לחץ על `Customize`. תחת `Basics` > `Search engine ID`, העתק את ה-**Search engine ID** (שנקרא גם CX).

### שלב 3: הגדרת בסיס נתונים (אופציונלי, לסטטיסטיקות)

1.  **צור חשבון חינמי** ב-[MongoDB Atlas](https://www.mongodb.com/cloud/atlas/register).
2.  **צור קלאסטר (Cluster)** חינמי.
3.  **צור משתמש לבסיס הנתונים** ושמור את פרטיו.
4.  **אפשר גישה מכל מקום** (`Allow Access from Anywhere`).
5.  **העתק את כתובת ההתחברות (Connection String)** והחלף בה את שם המשתמש והסיסמה.

### שלב 4: העלאת הפרויקט ל-GitHub

1.  צור מאגר (repository) חדש בחשבון ה-GitHub שלך.
2.  העלה את כל קבצי הפרויקט למאגר זה (`main.py`, `tools.json`, `requirements.txt`, `render.yaml`, וקובץ `README.md` זה).

### שלב 5: הגדרת הפרויקט ב-Render

1.  לחץ על **New +** ובחר **Blueprint**. חבר את מאגר ה-GitHub שלך.
2.  Render יזהה את קובץ `render.yaml`. תן שם לשירות.
3.  עבור ללשונית **Environment**.
4.  תחת **Secret Files**, צור קובץ בשם `.env` עם התוכן הבא (החלף בערכים שאספת):

    ```
    # --- Telegram & Bot Admin ---
    BOT_TOKEN=הטוקן_של_הבוט_שלך_מטלגרם
    ADMIN_ID=ה-ID_שלך_מטלגרם

    # --- AI & Database ---
    GROQ_API_KEY=מפתח_ה-API_שלך_מ-Groq
    MONGO_URI=כתובת_ההתחברות_שלך_מ-MongoDB_Atlas

    # --- Google Live Search ---
    GOOGLE_SEARCH_API_KEY=מפתח_ה-API_שלך_מגוגל_קלאוד
    CUSTOM_SEARCH_ENGINE_ID=מזהה_מנוע_החיפוש_שלך_(CX)
    ```

5.  לחץ על **Create New Web Service**.

### שלב 6: הגדרת Keep-Alive

1.  העתק את כתובת ה-URL של השירות שלך מ-Render.
2.  ב-[UptimeRobot](https://uptimerobot.com/), צור **New Monitor** מסוג `HTTP(s)`.
3.  הדבק את ה-URL והגדר את **Monitoring Interval** ל-`Every 5 minutes`.

---

### 🌐 שירותים חיצוניים

הבוט מסתמך על מספר שירותים חיצוניים כדי לפעול:
* **[Render](https://render.com/):** פלטפורמת הענן שמריצה את הבוט 24/7.
* **[Groq](https://groq.com/):** מספקת את מודל השפה המהיר להבנת בקשות ולסיכום תוצאות.
* **[Google Programmable Search](https://programmablesearchengine.google.com/):** מאפשר לבצע חיפוש חי ועדכני באינטרנט.
* **[MongoDB Atlas](https://www.mongodb.com/cloud/atlas):** בסיס הנתונים שבו נשמרים פרטי המשתמשים לסטטיסטיקה.
* **[UptimeRobot](https://uptimerobot.com/):** שירות הניטור ששומר על הבוט "ער" ומונע ממנו להירדם.
