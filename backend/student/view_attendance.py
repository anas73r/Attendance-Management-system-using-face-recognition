from flask import Blueprint, request, jsonify, current_app
from datetime import datetime
import time
from utils import normalize_student_id

attendance_bp = Blueprint("attendance", __name__)

# ------------------------- GET ATTENDANCE -------------------------
@attendance_bp.route('/api/attendance', methods=['GET'])
def get_attendance():
    db = current_app.config.get("DB")
    # CRITICAL: Attendance records are in a different DB context
    attendance_col = current_app.config.get("ATTENDANCE_COLLECTION")
    students_col = db.students

    date = request.args.get('date')
    department = request.args.get('department')
    year = request.args.get('year')
    division = request.args.get('division')
    subject = request.args.get('subject')
    student_id = request.args.get('student_id')

    try:
        current_app.logger.info(f"🔍 Fetching attendance for Date: {date}, Sub: {subject}, Dept: {department}")
        
        # Query attendance collection
        query = {}
        if date: query["date"] = str(date)
        if department: query["department"] = str(department)
        if year: query["year"] = str(year)
        if division: query["division"] = str(division)
        if subject: query["subject"] = str(subject)

        attendance_doc = attendance_col.find_one(query)
        if not attendance_doc:
            current_app.logger.warning(f"⚠️ No attendance document found for query: {query}")

        # Build roster from students collection for given class filters
        roster_filter = {}
        if department: roster_filter["department"] = str(department)
        if year: roster_filter["year"] = str(year)
        if division: roster_filter["division"] = str(division)

        roster = list(students_col.find(roster_filter)) if roster_filter else []
        current_app.logger.info(f"👥 Roster found: {len(roster)} students")

        # Map session students by id for quick lookup
        session_map = {}
        if attendance_doc:
            for s in attendance_doc.get("students", []):
                raw_sid = s.get("student_id") or s.get("studentId")
                sid = normalize_student_id(raw_sid)
                if sid:
                    session_map[sid] = s
            current_app.logger.info(f"✅ Session map created with {len(session_map)} students")

        attendance_list = []
        seen_students = set()

        # Merge roster and session students: show present and absent
        for student in roster:
            raw_sid = student.get("studentId") or student.get("student_id")
            sid = normalize_student_id(raw_sid)
            if not sid or sid in seen_students:
                continue
            seen_students.add(sid)
            
            # Apply student_id filter if provided
            if student_id and sid != normalize_student_id(student_id):
                continue

            sess = session_map.get(sid)
            if sess:
                present = bool(sess.get("present"))
                marked_at = sess.get("marked_at")
                if marked_at is not None:
                    try:
                        marked_at = marked_at.isoformat() if hasattr(marked_at, 'isoformat') else str(marked_at)
                    except:
                        marked_at = str(marked_at)
            else:
                present = False
                marked_at = None

            attendance_list.append({
                "studentId": str(sid),
                "studentName": student.get("studentName") or student.get("student_name") or "Unknown",
                "date": str(attendance_doc.get("date")) if attendance_doc else str(date),
                "subject": str(attendance_doc.get("subject")) if attendance_doc else str(subject),
                "department": str(attendance_doc.get("department")) if attendance_doc else str(department),
                "year": str(attendance_doc.get("year")) if attendance_doc else str(year),
                "division": str(attendance_doc.get("division")) if attendance_doc else str(division),
                "status": "present" if present else "absent",
                "markedAt": marked_at
            })

        # Also include any session-only students not in roster
        if attendance_doc:
            for s in attendance_doc.get("students", []):
                raw_sid = s.get("student_id") or s.get("studentId")
                sid = normalize_student_id(raw_sid)
                if not sid or sid in seen_students:
                    continue
                if student_id and sid != normalize_student_id(student_id):
                    continue
                seen_students.add(sid)
                
                marked = s.get("marked_at")
                if marked is not None:
                    try:
                        marked = marked.isoformat() if hasattr(marked, 'isoformat') else str(marked)
                    except:
                        marked = str(marked)

                attendance_list.append({
                    "studentId": str(sid),
                    "studentName": s.get("student_name") or "Unknown",
                    "date": str(attendance_doc.get("date")),
                    "subject": str(attendance_doc.get("subject")),
                    "department": str(attendance_doc.get("department")),
                    "year": str(attendance_doc.get("year")),
                    "division": str(attendance_doc.get("division")),
                    "status": "present" if s.get("present") else "absent",
                    "markedAt": marked
                })

        total_students = len(roster)
        present_count = sum(1 for r in attendance_list if r.get("status") == "present")
        absent_count = max(total_students - present_count, 0)
        attendance_rate = round((present_count / total_students * 100) if total_students > 0 else 0, 1)

        return jsonify({
            "success": True,
            "attendance": attendance_list,
            "stats": {
                "totalStudents": total_students,
                "presentToday": present_count,
                "absentToday": absent_count,
                "attendanceRate": attendance_rate
            }
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ------------------------- EXPORT TO EXCEL -------------------------
@attendance_bp.route('/api/attendance/export', methods=['GET'])
def export_attendance():
    db = current_app.config.get("DB")
    # CRITICAL: Attendance records are in a different DB context
    attendance_col = current_app.config.get("ATTENDANCE_COLLECTION")
    students_col = db.students

    date = request.args.get('date')
    department = request.args.get('department')
    year = request.args.get('year')
    division = request.args.get('division')
    subject = request.args.get('subject')

    try:
        current_app.logger.info(f"📤 Exporting attendance for Date: {date}, Sub: {subject}")
        # Get attendance doc
        query = {}
        if date: query["date"] = str(date)
        if department: query["department"] = str(department)
        if year: query["year"] = str(year)
        if division: query["division"] = str(division)
        if subject: query["subject"] = str(subject)

        attendance_doc = attendance_col.find_one(query)
        present_ids = set()

        if attendance_doc:
            for entry in attendance_doc.get("students", []):
                raw_sid = entry.get("student_id") or entry.get("studentId")
                sid = normalize_student_id(raw_sid)
                if sid and entry.get("present"):
                    present_ids.add(sid)
            current_app.logger.info(f"✅ Found {len(present_ids)} present students for export")

        # Get all students in that class
        student_filter = {}
        if department: student_filter["department"] = str(department)
        if year: student_filter["year"] = str(year)
        if division: student_filter["division"] = str(division)

        students = list(students_col.find(student_filter))
        export_data = []

        for student in students:
            raw_sid = student.get("studentId") or student.get("student_id")
            sid = normalize_student_id(raw_sid)
            if not sid: continue
            
            name = student.get("studentName") or student.get("student_name") or "Unknown"
            status = "present" if sid in present_ids else "absent"
            
            export_data.append({
                "studentId": str(sid),
                "name": name,
                "subject": str(subject) if subject else "N/A",
                "date": str(date) if date else "N/A",
                "status": status
            })
            if status == "present":
                current_app.logger.info(f"📤 Export: {name} ({sid}) -> present")

        return jsonify({"success": True, "data": export_data})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500