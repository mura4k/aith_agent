import sqlite3
import json
import os

class Database:
    def __init__(self, db_path='sessions.db'):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.init_db()

    def init_db(self):
        with self.conn:
            self.conn.execute('''
                CREATE TABLE IF NOT EXISTS sessions (
                    userId TEXT PRIMARY KEY,
                    state TEXT,
                    sheetUrl TEXT,
                    userName TEXT,
                    userIdInSheet TEXT,
                    selectedCourses TEXT,
                    creditsEarned REAL DEFAULT 0,
                    mandatoryCredits REAL DEFAULT 0,
                    lastMessageId INTEGER
                )
            ''')

    def get_session(self, user_id):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM sessions WHERE userId = ?', (str(user_id),))
        row = cursor.fetchone()
        if not row:
            return None
        
        session = dict(row)
        session['selectedCourses'] = json.loads(session['selectedCourses']) if session['selectedCourses'] else []
        return session

    def save_session(self, session):
        user_id = str(session['userId'])
        state = session.get('state', 'START')
        sheet_url = session.get('sheetUrl')
        user_name = session.get('userName')
        user_id_in_sheet = session.get('userIdInSheet')
        selected_courses = json.dumps(session.get('selectedCourses', []))
        credits_earned = session.get('creditsEarned', 0)
        mandatory_credits = session.get('mandatoryCredits', 0)

        with self.conn:
            self.conn.execute('''
                INSERT INTO sessions (userId, state, sheetUrl, userName, userIdInSheet, selectedCourses, creditsEarned, mandatoryCredits)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(userId) DO UPDATE SET
                    state = excluded.state,
                    sheetUrl = excluded.sheetUrl,
                    userName = excluded.userName,
                    userIdInSheet = excluded.userIdInSheet,
                    selectedCourses = excluded.selectedCourses,
                    creditsEarned = excluded.creditsEarned,
                    mandatoryCredits = excluded.mandatoryCredits
            ''', (user_id, state, sheet_url, user_name, user_id_in_sheet, selected_courses, credits_earned, mandatory_credits))

    def delete_session(self, user_id):
        with self.conn:
            self.conn.execute('DELETE FROM sessions WHERE userId = ?', (str(user_id),))
