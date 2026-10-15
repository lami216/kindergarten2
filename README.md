# نظام إدارة الروضة

> التقنية الفعلية Streamlit 1.61 + PostgreSQL (انظر db.py).
> إنشاء الطفل والأهل يتم الآن في صفحة الطلاب، وصفحة الأهل للبحث والعرض والتعديل.
> صفحة الأقسام تدير أسماء الأقسام ونقل الأطفال، والسجل القديم يبقى محفوظًا.


## 🗂️ هيكلة المشروع (وحدات مستقلة)
```
app.py              → نقطة التشغيل فقط (إعداد الصفحة + تسجيل الدخول + التوجيه بين الشاشات)
sidebar.py           → القائمة الجانبية (الشعار، الإحصائيات السريعة، أزرار التنقل)
auth.py               → شاشة تسجيل الدخول
ui.py                  → عناصر مشتركة (بطاقات، عناوين الأقسام، الشعار...)
receipt.py            → وصل الدفع القابل للطباعة بضغطة واحدة
style.py               → التنسيق العام (الألوان، الاستجابة للجوال)
db.py / helpers.py     → قاعدة البيانات والمنطق المشترك (لا تُعدَّل عادة)

sections/
    dashboard.py        → لوحة التحكم
    students.py          → الطلاب
    parents.py            → أولياء الأمور
    teachers.py            → المعلمون
    classes.py              → الصفوف
    academic_years.py        → السنوات الدراسية
    registration.py           → التسجيل
    payments.py                → الدفعات المالية
    reports.py                  → التقارير
```

## التشغيل والتحديث

يتطلب Python 3.12 وPostgreSQL. ثبّت `requirements.txt` كما هو، ثم ضع رابط PostgreSQL وحساب المسؤول في `.streamlit/secrets.toml` وفق إعدادات المصادقة. لا تُحفظ الأسرار في Git.

قبل تشغيل التطبيق لأول مرة **وعند كل تحديث**، نفّذ في خطوة النشر المستقلة:

```sh
python -m schema_migrations
streamlit run app.py
```

يمكن قراءة الرابط من متغير بيئة بدل ملف الأسرار: `python -m schema_migrations --dsn-env DATABASE_URL`.
الترحيل مرقّم ويُنفذ داخل معاملة واحدة بقفل يمنع تداخل تحديثين. عند الفشل يتراجع التحديث كاملًا. خذ نسخة PostgreSQL قابلة للاستعادة قبل تحديث قاعدة فعلية. حساب الترحيل يحتاج صلاحية تعديل البنية؛ لا تشغله استجابة لزيارة المستخدم.

فتح الصفحات يتحقق من الإصدار فقط، ويتوقف برسالة تحديث إذا لم يكتمل. لا ينشئ جداول أو يحذف آليات التدقيق. إصدار أقدم من التطبيق لا يقبل قاعدة أحدث.

العمل اليومي: أضف الأقسام، واضبط الرسوم، ثم سجّل الطلاب وما دفعوه والمصروفات. ملف ZIP في القائمة تصدير جميع جداول البيانات مع فهرس وتحقق، وليس نسخة PostgreSQL جاهزة للاستعادة. معاينة GitHub Pages مستقلة عن قاعدة التطبيق.


<img width="1287" height="895" alt="image" src="https://github.com/user-attachments/assets/75c9a208-c805-48d4-9de8-1a1c8b434a82" />



<img width="1910" height="930" alt="image" src="https://github.com/user-attachments/assets/ac06a2f2-b60c-4e62-a93d-4bc50670cfeb" />



<img width="1912" height="922" alt="image" src="https://github.com/user-attachments/assets/b68391db-4ab4-4861-8fc0-efdbdc23055e" />


<img width="1905" height="841" alt="image" src="https://github.com/user-attachments/assets/6f9e0039-d379-441b-a070-e0c17efa9a31" />

