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
import time

# File locking (optional - may not be available on all systems)
try:
    import fcntl
    HAS_FCNTL = True
except ImportError:
    HAS_FCNTL = False

try:
    from app.core.config_simple import settings
except ImportError:
    settings = None


class AzureSQLService:
    """Azure SQL Database service"""
    
    # In-memory storage for mock mode (when Azure SQL is not configured)
    _mock_storage: Dict[str, Dict] = {}
    # Use /tmp directory (writable in Azure App Service) or current directory as fallback
    _mock_storage_file: str = os.getenv("MOCK_STORAGE_FILE", "/tmp/gait_analysis_mock_storage.json")
    
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
            logger.warning("Azure SQL not configured - using file-based mock storage")
            self.connection_string = None
            self._use_mock = True
            # Ensure class variable exists (in case it was cleared)
            if not hasattr(AzureSQLService, '_mock_storage') or AzureSQLService._mock_storage is None:
                AzureSQLService._mock_storage = {}
            # Load from file if it exists (persist across restarts)
            self._load_mock_storage()
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
    
    def _load_mock_storage(self):
        """Load mock storage from file if it exists"""
        try:
            if os.path.exists(AzureSQLService._mock_storage_file):
                # Use file locking to prevent race conditions (if available)
                with open(AzureSQLService._mock_storage_file, 'r') as f:
                    if HAS_FCNTL:
                        try:
                            fcntl.flock(f.fileno(), fcntl.LOCK_SH)  # Shared lock for reading
                            data = json.load(f)
                        finally:
                            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                    else:
                        data = json.load(f)
                    
                    AzureSQLService._mock_storage = data
                    logger.info(f"Loaded {len(AzureSQLService._mock_storage)} analyses from mock storage file: {AzureSQLService._mock_storage_file}")
            else:
                logger.debug(f"Mock storage file does not exist yet: {AzureSQLService._mock_storage_file}")
                if not AzureSQLService._mock_storage:
                    AzureSQLService._mock_storage = {}
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in mock storage file: {e}. Resetting storage.")
            AzureSQLService._mock_storage = {}
        except Exception as e:
            logger.warning(f"Failed to load mock storage from file: {e}")
            if not AzureSQLService._mock_storage:
                AzureSQLService._mock_storage = {}
    
    def _save_mock_storage(self):
        """Save mock storage to file with file locking"""
        logger.info(f"SAVE: Starting save operation for {len(AzureSQLService._mock_storage)} analyses to {AzureSQLService._mock_storage_file}")
        try:
            # Ensure directory exists
            storage_dir = os.path.dirname(AzureSQLService._mock_storage_file)
            if storage_dir and storage_dir != '/':
                try:
                    os.makedirs(storage_dir, exist_ok=True)
                    logger.debug(f"SAVE: Directory {storage_dir} exists or created")
                except Exception as e:
                    logger.warning(f"SAVE: Could not create directory {storage_dir}: {e}")
            
            # Use atomic write with file locking (if available)
            temp_file = AzureSQLService._mock_storage_file + '.tmp'
            logger.info(f"SAVE: Attempting to save {len(AzureSQLService._mock_storage)} analyses to {temp_file}")
            
            # Check if we can write to the directory
            try:
                test_file = os.path.join(storage_dir if storage_dir else '/tmp', '.write_test')
                with open(test_file, 'w') as tf:
                    tf.write('test')
                os.unlink(test_file)
                logger.debug(f"SAVE: Write test successful in {storage_dir if storage_dir else '/tmp'}")
            except Exception as e:
                logger.error(f"SAVE: Cannot write to directory {storage_dir if storage_dir else '/tmp'}: {e}")
            
            with open(temp_file, 'w') as f:
                logger.debug(f"SAVE: Opened temp file {temp_file} for writing")
                if HAS_FCNTL:
                    try:
                        fcntl.flock(f.fileno(), fcntl.LOCK_EX)  # Exclusive lock for writing
                        json.dump(AzureSQLService._mock_storage, f, indent=2)
                        f.flush()
                        os.fsync(f.fileno())  # Force write to disk
                        logger.debug(f"SAVE: Wrote data with file locking")
                    finally:
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                else:
                    json.dump(AzureSQLService._mock_storage, f, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                    logger.debug(f"SAVE: Wrote data without file locking")
            
            # Atomic rename
            logger.debug(f"SAVE: Attempting atomic rename from {temp_file} to {AzureSQLService._mock_storage_file}")
            os.replace(temp_file, AzureSQLService._mock_storage_file)
            logger.info(f"SAVE: Successfully saved {len(AzureSQLService._mock_storage)} analyses to mock storage file: {AzureSQLService._mock_storage_file}. IDs: {list(AzureSQLService._mock_storage.keys())}")
            
            # Verify file was created
            if os.path.exists(AzureSQLService._mock_storage_file):
                file_size = os.path.getsize(AzureSQLService._mock_storage_file)
                logger.info(f"SAVE: Storage file verified: {AzureSQLService._mock_storage_file} ({file_size} bytes)")
            else:
                logger.error(f"SAVE: Storage file was not created after rename: {AzureSQLService._mock_storage_file}")
        except PermissionError as e:
            logger.error(f"SAVE: Permission denied saving mock storage to {AzureSQLService._mock_storage_file}: {e}", exc_info=True)
        except OSError as e:
            logger.error(f"SAVE: OS error saving mock storage: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"SAVE: Failed to save mock storage to file: {e}", exc_info=True)
    
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
            # Store in in-memory mock storage (use class variable to ensure persistence)
            from datetime import datetime
            analysis_id = analysis_data.get('id')
            AzureSQLService._mock_storage[analysis_id] = {
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
            logger.debug(f"About to save mock storage with {len(AzureSQLService._mock_storage)} analyses")
            self._save_mock_storage()  # Persist to file
            logger.info(f"Created analysis in mock storage: {analysis_id}. Total analyses: {len(AzureSQLService._mock_storage)}")
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
            # Update in-memory mock storage (use class variable to ensure persistence)
            if analysis_id in AzureSQLService._mock_storage:
                from datetime import datetime
                AzureSQLService._mock_storage[analysis_id].update(updates)
                AzureSQLService._mock_storage[analysis_id]['updated_at'] = datetime.now().isoformat()
                logger.debug(f"About to save mock storage after update. Total analyses: {len(AzureSQLService._mock_storage)}")
                self._save_mock_storage()  # Persist to file
                logger.debug(f"Updated analysis in mock storage: {analysis_id}")
                return True
            logger.warning(f"Analysis not found in mock storage: {analysis_id}. Available IDs: {list(AzureSQLService._mock_storage.keys())}")
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
            # Reload from file to ensure we have latest data (handles multi-process scenarios)
            self._load_mock_storage()
            # Get from in-memory mock storage (use class variable to ensure persistence)
            if analysis_id in AzureSQLService._mock_storage:
                logger.debug(f"Retrieved analysis from mock storage: {analysis_id}")
                return AzureSQLService._mock_storage[analysis_id].copy()
            logger.warning(f"Analysis not found in mock storage: {analysis_id}. Available IDs: {list(AzureSQLService._mock_storage.keys())}. Storage file: {AzureSQLService._mock_storage_file}")
            # Try one more time to load from file (in case it was just written)
            time.sleep(0.1)
            self._load_mock_storage()
            if analysis_id in AzureSQLService._mock_storage:
                logger.info(f"Found analysis after retry: {analysis_id}")
                return AzureSQLService._mock_storage[analysis_id].copy()
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
    
    async def list_analyses(self, limit: int = 50) -> List[Dict]:
        """List all analyses, ordered by most recent first"""
        if self._use_mock:
            # Reload from file to ensure we have latest data
            self._load_mock_storage()
            # Get all from in-memory mock storage (use class variable to ensure persistence)
            analyses = list(AzureSQLService._mock_storage.values())
            # Sort by created_at descending
            analyses.sort(key=lambda x: x.get('created_at', ''), reverse=True)
            return analyses[:limit]
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, patient_id, filename, video_url, status, 
                           current_step, step_progress, step_message, 
                           metrics, created_at, updated_at
                    FROM analyses
                    ORDER BY created_at DESC
                    OFFSET 0 ROWS FETCH NEXT ? ROWS ONLY
                """, (limit,))
                
                rows = cursor.fetchall()
                analyses = []
                for row in rows:
                    metrics = json.loads(row[8]) if row[8] else {}
                    analyses.append({
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
                    })
                return analyses
        except Exception as e:
            logger.error(f"Failed to list analyses: {e}")
            return []



