"""Resolve audit references in batches without changing immutable history."""


def decorate(conn, entries):
    if not entries:
        return entries
    records = [state for entry in entries for state in (entry['before'], entry['after']) if state]
    keys = {key: sorted({str(row[key]) for row in records if row.get(key) is not None})
            for key in ('student_id', 'father_id', 'national_id', 'teacher_id', 'department_id', 'person_id')}
    students = sorted(set(keys['student_id'] + keys['person_id']))
    teachers = sorted(set(keys['national_id'] + keys['teacher_id'] + keys['person_id']))
    def names(query, values):
        if not values:
            return {}
        with conn.cursor() as cursor:
            cursor.execute(query, (values,))
            return {str(row['id']): row['label'] for row in cursor.fetchall()}
    maps = {
        'students': names('SELECT student_id AS id,full_name AS label FROM students WHERE student_id=ANY(%s)', students),
        'teachers': names("SELECT national_id AS id,full_name||' · '||COALESCE(display_national_id,national_id) AS label FROM teachers WHERE national_id=ANY(%s)", teachers),
        'parents': names("SELECT father_id AS id,concat_ws(' · ',COALESCE(father_name,mother_name),COALESCE(father_mobile,mother_mobile)) AS label FROM parents WHERE father_id=ANY(%s)", keys['father_id']),
        'departments': names('SELECT department_id AS id,name AS label FROM school_departments WHERE department_id::text=ANY(%s)', keys['department_id']),
    }
    output = []
    for entry in entries:
        kind = entry['type']
        def reference_labels(state):
            result = {}
            for key, group in (('student_id','students'),('father_id','parents'),('department_id','departments'),
                               ('national_id','teachers'),('teacher_id','teachers'),
                               ('person_id','teachers' if kind=='teacher_attendance' else 'students')):
                value = (state or {}).get(key)
                if value is not None and str(value) in maps[group]:
                    result[key] = maps[group][str(value)]
            return result
        before_labels, after_labels = reference_labels(entry['before']), reference_labels(entry['after'])
        before, after = entry['before'] or {}, entry['after'] or {}
        subject = (after.get('full_name') or after.get('name') or after.get('category') or after.get('item_name') or
                   before.get('full_name') or before.get('name') or before.get('category') or
                   after.get('father_name') or after.get('mother_name') or before.get('father_name') or before.get('mother_name'))
        if not subject:
            labels = {**before_labels, **after_labels}
            subject = next((labels[key] for key in ('student_id','national_id','person_id','teacher_id','father_id','department_id') if key in labels), None)
        output.append({**entry, 'subject': subject, 'before_labels': before_labels, 'after_labels': after_labels})
    return output
