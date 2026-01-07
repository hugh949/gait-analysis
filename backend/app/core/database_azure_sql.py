"""
Azure SQL Database Service
Simple relational database using Microsoft managed service
"""
from typing import Optional, Dict, List
import pyodbc
from contextlib import contextmanager
from loguru import logger
import os
import json

try:
    from app.core.config_simple import settings
except ImportError:
    settings = None


class AzureSQLService:
    """Azure SQL Database service"""
    
    # In-memory storage for mock mode (when Azure SQL is not configured)
    _mock_storage: Dict[str, Dict] = {}
    
    def __init__(self):
        """Initialize Azure SQL Database connection"""
        self.server = os.getenv(
            "AZURE_SQL_SERVER",
            getattr(settings, "AZURE_SQL_SERVER", None) if settings else None
        )
        self.database = os.getenv(
            "AZURE_SQL_DATABASE",
            getattr(settings, "AZURE_SQL_DATABASE", "gaitanalysis") if settings else "gaitanalysis"
        )
        self.username = os.getenv(
            "AZURE_SQL_USER",
            getattr(settings, "AZURE_SQL_USER", None) if settings else None
        )
        self.password = os.getenv(
            "AZURE_SQL_PASSWORD",
            getattr(settings, "AZURE_SQL_PASSWORD", None) if settings else None
        )
        
        if not all([self.server, self.username, self.password]):
            logger.warning("Azure SQL not configured - using in-memory mock storage")
            self.connection_string = None
            self._use_mock = True
        else:
            self._use_mock = False
            # Build connection string
            driver = "{ODBC Driver 18 for SQL Server}"
            self.connection_string = (
                f"Driver={driver};"
                f"Server=tcp:{self.server},1433;"
                f"Database={self.database};"
                f"Uid={self.username};"
                f"Pwd={self.password};"
                f"Encrypt=yes;"
                f"TrustServerCertificate=no;"
                f"Connection Timeout=30;"
            )
            logger.info(f"Azure SQL initialized: {self.server}/{self.database}")
            
            # Initialize database schema
            self._init_schema()
    
    def _init_schema(self):
        """Initialize database schema"""
        if not self.connection_string:
            return
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Create analyses table
                cursor.execute("""
                    IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'analyses')
                    CREATE TABLE analyses (
                        id NVARCHAR(100) PRIMARY KEY,
                        patient_id NVARCHAR(100),
                        filename NVARCHAR(500),
                        video_url NVARCHAR(1000),
                        status NVARCHAR(50),
                        current_step NVARCHAR(100),
                        step_progress INT,
                        step_message NVARCHAR(1000),
                        metrics NVARCHAR(MAX),
                        created_at DATETIME2 DEFAULT GETDATE(),
                        updated_at DATETIME2 DEFAULT GETDATE()
                    )
                """)
                
                # Create index on status for faster queries
                cursor.execute("""
                    IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_analyses_status')
                    CREATE INDEX idx_analyses_status ON analyses(status)
                """)
                
                conn.commit()
                logger.info("Database schema initialized")
        
        except Exception as e:
            logger.error(f"Failed to initialize schema: {e}")
    
    @contextmanager
    def get_connection(self):
        """Get database connection"""
        if not self.connection_string:
            # Mock connection
            class MockConnection:
                def cursor(self):
                    return MockCursor()
                def commit(self):
                    pass
                def close(self):
                    pass
            
            class MockCursor:
                def execute(self, *args):
                    pass
                def fetchone(self):
                    return None
                def fetchall(self):
                    return []
                def close(self):
                    pass
            
            yield MockConnection()
            return
        
        conn = None
        try:
            conn = pyodbc.connect(self.connection_string)
            yield conn
        except Exception as e:
            logger.error(f"Database connection error: {e}")
            raise
        finally:
            if conn:
                conn.close()
    
    async def create_analysis(self, analysis_data: Dict) -> bool:
        """Create new analysis record"""
        if self._use_mock:
            # Store in in-memory mock storage
            from datetime import datetime
            analysis_id = analysis_data.get('id')
            self._mock_storage[analysis_id] = {
                'id': analysis_id,
                'patient_id': analysis_data.get('patient_id'),
                'filename': analysis_data.get('filename'),
                'video_url': analysis_data.get('video_url'),
                'status': analysis_data.get('status', 'processing'),
                'current_step': analysis_data.get('current_step', 'pose_estimation'),
                'step_progress': analysis_data.get('step_progress', 0),
                'step_message': analysis_data.get('step_message', 'Initializing...'),
                'metrics': analysis_data.get('metrics', {}),
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            }
            logger.info(f"Created analysis in mock storage: {analysis_id}")
            return True
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO analyses 
                    (id, patient_id, filename, video_url, status, current_step, step_progress, step_message)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    analysis_data.get('id'),
                    analysis_data.get('patient_id'),
                    analysis_data.get('filename'),
                    analysis_data.get('video_url'),
                    analysis_data.get('status', 'processing'),
                    analysis_data.get('current_step', 'pose_estimation'),
                    analysis_data.get('step_progress', 0),
                    analysis_data.get('step_message', 'Initializing...')
                ))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to create analysis: {e}")
            return False
    
    async def update_analysis(self, analysis_id: str, updates: Dict) -> bool:
        """Update analysis record"""
        if self._use_mock:
            # Update in-memory mock storage
            if analysis_id in self._mock_storage:
                from datetime import datetime
                self._mock_storage[analysis_id].update(updates)
                self._mock_storage[analysis_id]['updated_at'] = datetime.now().isoformat()
                logger.debug(f"Updated analysis in mock storage: {analysis_id}")
                return True
            logger.warning(f"Analysis not found in mock storage: {analysis_id}")
            return False
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Build update query dynamically
                set_clauses = []
                values = []
                
                for key, value in updates.items():
                    if key in ['status', 'current_step', 'step_progress', 'step_message', 'metrics', 'video_url']:
                        set_clauses.append(f"{key} = ?")
                        if key == 'metrics' and isinstance(value, dict):
                            values.append(json.dumps(value))
                        else:
                            values.append(value)
                
                if set_clauses:
                    set_clauses.append("updated_at = GETDATE()")
                    values.append(analysis_id)
                    
                    query = f"UPDATE analyses SET {', '.join(set_clauses)} WHERE id = ?"
                    cursor.execute(query, values)
                    conn.commit()
                    return True
                return False
        except Exception as e:
            logger.error(f"Failed to update analysis: {e}")
            return False
    
    async def get_analysis(self, analysis_id: str) -> Optional[Dict]:
        """Get analysis record"""
        if self._use_mock:
            # Get from in-memory mock storage
            if analysis_id in self._mock_storage:
                logger.debug(f"Retrieved analysis from mock storage: {analysis_id}")
                return self._mock_storage[analysis_id].copy()
            logger.debug(f"Analysis not found in mock storage: {analysis_id}")
            return None
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, patient_id, filename, video_url, status, 
                           current_step, step_progress, step_message, 
                           metrics, created_at, updated_at
                    FROM analyses
                    WHERE id = ?
                """, (analysis_id,))
                
                row = cursor.fetchone()
                if row:
                    metrics = json.loads(row[8]) if row[8] else {}
                    return {
                        'id': row[0],
                        'patient_id': row[1],
                        'filename': row[2],
                        'video_url': row[3],
                        'status': row[4],
                        'current_step': row[5],
                        'step_progress': row[6],
                        'step_message': row[7],
                        'metrics': metrics,
                        'created_at': str(row[9]),
                        'updated_at': str(row[10])
                    }
                return None
        except Exception as e:
            logger.error(f"Failed to get analysis: {e}")
            return None



