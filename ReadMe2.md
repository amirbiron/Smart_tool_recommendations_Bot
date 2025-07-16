# 🤖 בוט המלצות כלים חכמים - מדריך הפעלה ופריסה

מדריך זה ילווה אותך צעד אחר צעד בהפעלת הבוט שלך על שרתי Render, תוך שימוש ב-Google Colab לבנייה חד-פעמית של מאגר הנתונים.

---

### שלב 1: בניית "המוח" של הבוט (פעולה חד-פעמית ב-Google Colab)

זהו השלב החשוב ביותר. נשתמש בשרתים החינמיים של גוגל כדי לבנות את קבצי האינדקס.

1.  **פתח את Google Colab:**
    * [לחץ כאן כדי לפתוח מחברת Colab חדשה](https://colab.research.google.com/).
2.  **התקן את הספריות הנדרשות:**
    * בתא הקוד הראשון, הדבק והרץ את הפקודה הבאה:
      ```
      !pip install sentence-transformers faiss-cpu
      ```
3.  **העלה את מאגר הכלים שלך:**
    * בתפריט הצד השמאלי, לחץ על סמל התיקייה.
    * לחץ על סמל העלאת הקבצים והעלה את קובץ ה-`tools.json` המלא שלך.
4.  **הדבק והרץ את סקריפט הבנייה:**
    * צור תא קוד חדש, והדבק בו את כל הקוד מקובץ `create_embeddings.py` שסיפקתי לך.
    * הרץ את התא. התהליך ייקח כמה דקות.
5.  **הורד את התוצאות:**
    * בסיום הריצה, שני קבצים חדשים יופיעו בחלונית הקבצים: `tools.faiss` ו-`index_to_name.json`.
    * הורד את שני הקבצים האלה למחשב/לנייד שלך.

---

### שלב 2: העלאת הפרויקט המלא ל-GitHub

1.  צור מאגר (repository) חדש בחשבון ה-GitHub שלך.
2.  העלה למאגר את **כל** הקבצים:
    * `main.py` (הגרסה הסופית)
    * `tools.json` (המאגר המלא)
    * `requirements.txt`
    * `render.yaml` (הגרסה ללא הדיסק)
    * **`tools.faiss`** (הקובץ שהורדת מ-Colab)
    * **`index_to_name.json`** (הקובץ שהורדת מ-Colab)

---

### שלב 3: הגדרת הפרויקט ב-Render

1.  **צור Web Service חדש:**
    * ב-Render, לחץ על **New +** ובחר **Web Service**.
    * חבר את מאגר ה-GitHub שלך.
    * ודא שהתוכנית היא **Free** ושכל ההגדרות נכונות.
2.  **הגדר משתני סביבה:**
    * עבור ללשונית **Environment** והוסף את כל המפתחות הסודיים שלך.
3.  **צור את השירות:**
    * לחץ על **Create Web Service**. הפעם, הפריסה **אמורה להצליח בפעם הראשונה**, כי כל הקבצים כבר קיימים.

---

### שלב 4: הגדרת Keep-Alive

הגדר מוניטור ב-[UptimeRobot](https://uptimerobot.com/) שיפנה לכתובת הבוט שלך כל 5 דקות.
