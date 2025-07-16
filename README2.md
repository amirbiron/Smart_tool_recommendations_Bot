
🤖 בוט המלצות כלים חכמים - מדריך הפעלה ופריסה
מדריך זה ילווה אותך צעד אחר צעד בהפעלת בוט הטלגרם שלך על שרתי Render.

שלב 1: השגת מפתחות API ו-ID
אסוף את כל המפתחות הנדרשים מהשירותים השונים (טלגרם, Groq, MongoDB וכו') ושמור אותם בצד.

שלב 2: העלאת הפרויקט ל-GitHub
צור מאגר (repository) חדש בחשבון ה-GitHub שלך.

העלה את כל קבצי הפרויקט למאגר זה: main.py, tools.json, requirements.txt, render.yaml, וקובץ README.md זה.

שלב 3: הגדרת הפרויקט ב-Render
צור שירות חדש ב-Render באמצעות Blueprint.

עבור ללשונית Environment.

תחת Secret Files, צור קובץ .env עם כל המפתחות שלך.

לחץ על Create New Web Service. הפריסה הראשונית עלולה להיכשל כי קבצי האינדקס עדיין לא קיימים. זה צפוי וזה בסדר.

שלב 4: בניית "המוח" של הבוט (פעולה חד-פעמית)
לאחר שהשירות נוצר ב-Render (גם אם הוא במצב "נכשל"):

שלח לבוט שלך בטלגרם את הפקודה הסודית (שמוגדרת למנהל בלבד):
/rebuild_index

הבוט יתחיל בתהליך בניית האינדקס על השרת. זה עשוי לקחת מספר דקות. המתן בסבלנות.

בסיום, הבוט ישלח הודעת הצלחה.

לאחר קבלת ההודעה, לך ל-Render ולחץ על Manual Deploy > Deploy latest commit כדי להפעיל מחדש את הבוט עם האינדקס החדש והמוכן.

שלב 5: הגדרת Keep-Alive
הגדר מוניטור ב-UptimeRobot שיפנה לכתובת הבוט שלך כל 5 דקות כדי למנוע ממנו "להירדם".
