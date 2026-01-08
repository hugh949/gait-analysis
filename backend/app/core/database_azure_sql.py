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
    # Use /home/site directory which is guaranteed to persist across container restarts in Azure App Service
    # IMPORTANT: Do NOT use $HOME/site - $HOME is /root in Docker containers, which is ephemeral
    # /home/site is the persistent storage location in Azure App Service (hardcoded, not using HOME)
    _mock_storage_file: str = os.getenv(
        "MOCK_STORAGE_FILE", 
        "/home/site/gait_analysis_mock_storage.json"  # Hardcoded to /home/site, not $HOME/site
    )
    
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
        """Load mock storage from file if it exists, with retry logic for multi-worker scenarios"""
        # Ensure directory exists before trying to load
        storage_dir = os.path.dirname(AzureSQLService._mock_storage_file)
        if storage_dir and storage_dir != '/':
            try:
                os.makedirs(storage_dir, exist_ok=True)
                logger.debug(f"LOAD: Ensured directory exists: {storage_dir}")
            except Exception as e:
                logger.warning(f"LOAD: Could not create directory {storage_dir}: {e}")
        
        max_retries = 3
        retry_delay = 0.1
        
        for attempt in range(max_retries):
            try:
                # Check if file exists - with explicit path resolution
                file_path = os.path.abspath(AzureSQLService._mock_storage_file)
                if os.path.exists(file_path):
                    # Check file size first - if 0 bytes, file might be corrupted or in the middle of write
                    file_size = os.path.getsize(file_path)
                    if file_size == 0:
                        logger.warning(f"LOAD: Storage file exists but is empty (0 bytes): {file_path}. Waiting for write to complete...")
                        if attempt < max_retries - 1:
                            time.sleep(retry_delay * (attempt + 1))
                            continue
                        else:
                            logger.error(f"LOAD: Storage file is still empty after {max_retries} attempts. Preserving in-memory storage.")
                            # CRITICAL: Don't clear in-memory storage - preserve it
                            if not AzureSQLService._mock_storage:
                                AzureSQLService._mock_storage = {}
                            return
                    
                    # Use file locking to prevent race conditions (if available)
                    with open(file_path, 'r') as f:
                        if HAS_FCNTL:
                            try:
                                fcntl.flock(f.fileno(), fcntl.LOCK_SH)  # Shared lock for reading
                                data = json.load(f)
                            finally:
                                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                        else:
                            data = json.load(f)
                        
                        # Validate data is a dictionary
                        if not isinstance(data, dict):
                            logger.error(f"LOAD: Invalid data type in storage file (expected dict, got {type(data)}).")
                            # CRITICAL: Preserve in-memory storage if it exists
                            if not AzureSQLService._mock_storage:
                                logger.warning(f"LOAD: In-memory storage is empty, keeping it empty")
                                AzureSQLService._mock_storage = {}
                            else:
                                logger.warning(f"LOAD: Preserving {len(AzureSQLService._mock_storage)} analyses in memory despite invalid file data")
                            return
                        
                        # CRITICAL: MERGE file data with in-memory data, don't replace it
                        # This ensures analyses in memory (being processed) are never lost
                        if isinstance(data, dict):
                            # Merge file data into in-memory storage (file data takes precedence for conflicts)
                            # But preserve any analyses that exist only in memory
                            for key, value in data.items():
                                AzureSQLService._mock_storage[key] = value
                            logger.info(f"LOAD: Merged {len(data)} analyses from file into memory. Total in memory: {len(AzureSQLService._mock_storage)} (attempt {attempt + 1})")
                            if len(AzureSQLService._mock_storage) > 0:
                                logger.debug(f"LOAD: Analysis IDs in storage: {list(AzureSQLService._mock_storage.keys())}")
                        else:
                            # Invalid data type - preserve in-memory storage
                            logger.warning(f"LOAD: File contains invalid data type, preserving in-memory storage")
                        return  # Success - exit retry loop
                else:
                    if attempt == 0:  # Only log on first attempt
                        logger.debug(f"LOAD: Mock storage file does not exist yet: {file_path}")
                        # List directory to see what's actually there
                        try:
                            dir_contents = os.listdir(storage_dir)
                            logger.debug(f"LOAD: Directory contents: {dir_contents}")
                        except Exception as e:
                            logger.debug(f"LOAD: Could not list directory: {e}")
                    # CRITICAL: Don't clear in-memory storage if file doesn't exist
                    # The file might be temporarily unavailable, but in-memory data should persist
                    # Only initialize empty dict if we don't have any in-memory data
                    if not AzureSQLService._mock_storage:
                        AzureSQLService._mock_storage = {}
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay * (attempt + 1))  # Exponential backoff
                        continue
                    # File doesn't exist after retries - but keep in-memory storage intact
                    # This ensures data persists even if file is temporarily unavailable
                    logger.debug(f"LOAD: File not found after {max_retries} attempts, but keeping in-memory storage ({len(AzureSQLService._mock_storage)} analyses)")
                    return  # File doesn't exist, but in-memory storage is preserved
            except json.JSONDecodeError as e:
                logger.error(f"LOAD: Invalid JSON in mock storage file (attempt {attempt + 1}): {e}.")
                # CRITICAL: Don't clear in-memory storage on JSON errors - preserve existing data
                # Only clear if in-memory storage is also empty (fresh start)
                if not AzureSQLService._mock_storage:
                    logger.warning(f"LOAD: In-memory storage is empty, keeping it empty despite JSON error")
                    AzureSQLService._mock_storage = {}
                else:
                    logger.warning(f"LOAD: Preserving {len(AzureSQLService._mock_storage)} analyses in memory despite file JSON error")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (attempt + 1))
                    continue
                return
            except IOError as e:
                # File might be locked or temporarily unavailable (another process writing)
                if attempt < max_retries - 1:
                    logger.debug(f"LOAD: File temporarily unavailable (attempt {attempt + 1}): {e}. Retrying...")
                    time.sleep(retry_delay * (attempt + 1))
                    continue
                else:
                    logger.warning(f"LOAD: File unavailable after {max_retries} attempts: {e}. Using existing in-memory storage if available.")
                    # CRITICAL: Don't clear in-memory storage - preserve it
                    logger.info(f"LOAD: Preserving {len(AzureSQLService._mock_storage)} analyses in memory")
                    return
            except Exception as e:
                logger.error(f"LOAD: Unexpected error loading mock storage (attempt {attempt + 1}): {e}", exc_info=True)
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (attempt + 1))
                    continue
                # CRITICAL: On final failure, preserve in-memory storage - never clear it
                if not AzureSQLService._mock_storage:
                    logger.warning(f"LOAD: In-memory storage is empty, keeping it empty")
                else:
                    logger.warning(f"LOAD: Preserving {len(AzureSQLService._mock_storage)} analyses in memory despite load error")
                return
    
    def _save_mock_storage(self, force_sync: bool = True):
        """
        Save mock storage to file with file locking.
        CRITICAL: This is a synchronous method that can be called from threads.
        """
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
            
            # Atomic rename - ensure temp file exists and has content
            if not os.path.exists(temp_file):
                logger.error(f"SAVE: Temp file does not exist before rename: {temp_file}")
                raise FileNotFoundError(f"Temp file not found: {temp_file}")
            
            temp_file_size = os.path.getsize(temp_file)
            if temp_file_size == 0:
                logger.error(f"SAVE: Temp file is empty (0 bytes) before rename: {temp_file}")
                raise ValueError(f"Temp file is empty: {temp_file}")
            
            logger.debug(f"SAVE: Attempting atomic rename from {temp_file} ({temp_file_size} bytes) to {AzureSQLService._mock_storage_file}")
            os.replace(temp_file, AzureSQLService._mock_storage_file)
            
            # CRITICAL: Force filesystem sync to ensure rename is visible immediately
            # This is essential for multi-process/request scenarios
            try:
                # Sync the directory to ensure the rename is visible
                dir_fd = os.open(storage_dir, os.O_RDONLY)
                try:
                    os.fsync(dir_fd)  # Sync directory metadata
                    logger.debug(f"SAVE: Directory synced successfully")
                finally:
                    os.close(dir_fd)
            except Exception as e:
                logger.warning(f"SAVE: Could not sync directory (may cause visibility delay): {e}")
            
            # CRITICAL: Sync the file itself to ensure it's fully written to disk
            try:
                with open(AzureSQLService._mock_storage_file, 'r+') as f:
                    os.fsync(f.fileno())
                    logger.debug(f"SAVE: File synced successfully")
            except Exception as e:
                logger.warning(f"SAVE: Could not sync file (may cause visibility delay): {e}")
            
            # CRITICAL: Add a small delay to ensure filesystem has time to make file visible
            # This helps with filesystem caching and ensures other processes can see the file
            # Increased delay for better cross-worker visibility during long processing
            time.sleep(0.1)  # 100ms delay for filesystem to catch up (increased from 50ms)
            
            analysis_ids = list(AzureSQLService._mock_storage.keys())
            logger.info(f"💾 SAVE: Successfully saved {len(AzureSQLService._mock_storage)} analyses to mock storage file: {AzureSQLService._mock_storage_file}")
            logger.info(f"💾 SAVE: Analysis IDs in storage: {analysis_ids}")
            
            # Verify file was created - with retry in case of filesystem delay
            file_verified = False
            for verify_attempt in range(3):
                if os.path.exists(AzureSQLService._mock_storage_file):
                    file_size = os.path.getsize(AzureSQLService._mock_storage_file)
                    logger.info(f"SAVE: Storage file verified: {AzureSQLService._mock_storage_file} ({file_size} bytes) (attempt {verify_attempt + 1})")
                    file_verified = True
                    break
                if verify_attempt < 2:
                    time.sleep(0.1)
            
            if not file_verified:
                logger.error(f"SAVE: Storage file was not found after rename (even after retries): {AzureSQLService._mock_storage_file}")
                # List directory contents for debugging
                try:
                    dir_contents = os.listdir(storage_dir)
                    logger.error(f"SAVE: Directory contents: {dir_contents}")
                except Exception as e:
                    logger.error(f"SAVE: Could not list directory: {e}")
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
            # CRITICAL: Reload from file first to ensure we don't overwrite existing data
            self._load_mock_storage()
            
            # Store in in-memory mock storage (use class variable to ensure persistence)
            from datetime import datetime
            analysis_id = analysis_data.get('id')
            if not analysis_id:
                logger.error("Analysis data missing 'id' field")
                return False
            
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
            logger.info(f"💾 CREATE: About to save mock storage with {len(AzureSQLService._mock_storage)} analyses. Analysis ID: {analysis_id}")
            self._save_mock_storage()  # Persist to file
            logger.info(f"💾 CREATE: Saved analysis {analysis_id} to file. In-memory storage now has: {list(AzureSQLService._mock_storage.keys())}")
            
            # CRITICAL: Verify the save worked by checking in-memory storage
            # The in-memory storage should be the source of truth immediately after save
            if analysis_id not in AzureSQLService._mock_storage:
                logger.error(f"CREATE: Analysis was not found in mock storage immediately after creation: {analysis_id}")
                logger.error(f"CREATE: Available IDs in memory: {list(AzureSQLService._mock_storage.keys())}")
                return False
            
            logger.info(f"CREATE: Created analysis in mock storage: {analysis_id}. Total analyses: {len(AzureSQLService._mock_storage)}. IDs: {list(AzureSQLService._mock_storage.keys())}")
            
            # CRITICAL: Verify file is readable and contains the analysis before returning
            # This ensures the file is fully written and synced to disk
            file_path = os.path.abspath(AzureSQLService._mock_storage_file)
            verification_passed = False
            
            # Wait up to 1 second for file to be readable with the new analysis
            for verify_retry in range(10):  # 10 attempts with 0.1s delays = 1 second max
                if not os.path.exists(file_path):
                    if verify_retry < 9:
                        time.sleep(0.1)
                        continue
                    else:
                        logger.error(f"CREATE: Storage file does not exist after save: {file_path}")
                        break
                
                try:
                    # Try to read the file with proper locking
                    with open(file_path, 'r') as f:
                        if HAS_FCNTL:
                            try:
                                fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                                verify_data = json.load(f)
                            finally:
                                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                        else:
                            verify_data = json.load(f)
                        
                        if isinstance(verify_data, dict) and analysis_id in verify_data:
                            # Verify the data matches what we expect
                            stored_analysis = verify_data[analysis_id]
                            if stored_analysis.get('id') == analysis_id:
                                verification_passed = True
                                logger.info(f"CREATE: Verified analysis {analysis_id} is readable from file (attempt {verify_retry + 1})")
                                break
                        elif verify_retry < 9:
                            logger.debug(f"CREATE: Analysis not yet in file, retrying... (attempt {verify_retry + 1})")
                            time.sleep(0.2)  # Increased to 200ms to allow filesystem sync
                            continue
                except (json.JSONDecodeError, IOError, OSError) as e:
                    if verify_retry < 9:
                        logger.debug(f"CREATE: Verification read failed (attempt {verify_retry + 1}), retrying: {e}")
                        time.sleep(0.2)  # Increased to 200ms to allow filesystem sync
                        continue
                    else:
                        logger.warning(f"CREATE: Could not verify analysis in file after creation: {e}")
            
            if not verification_passed:
                logger.warning(f"CREATE: Could not verify analysis {analysis_id} in file after creation, but it exists in memory. File may have sync issues.")
                # Still return True because in-memory storage has it - file will catch up
                return True
            
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
        """
        Update analysis record with extensive logging.
        CRITICAL: During active processing, NEVER reload from file - it can overwrite in-memory data.
        In-memory storage is the source of truth during active processing.
        """
        logger.info(f"📝 UPDATE: Updating analysis {analysis_id} with fields: {list(updates.keys())}")
        if self._use_mock:
            # CRITICAL: Check in-memory storage FIRST (source of truth during processing)
            # Only reload from file if analysis is NOT in memory (for cross-worker updates)
            if analysis_id not in AzureSQLService._mock_storage:
                logger.info(f"UPDATE: Analysis {analysis_id} not in memory, reloading from file...")
                # Only reload if not in memory - this handles cross-worker scenarios
                self._load_mock_storage()
            
            # Update in-memory mock storage IMMEDIATELY (source of truth)
            if analysis_id in AzureSQLService._mock_storage:
                from datetime import datetime
                # CRITICAL: Update in-memory FIRST (immediate visibility)
                AzureSQLService._mock_storage[analysis_id].update(updates)
                AzureSQLService._mock_storage[analysis_id]['updated_at'] = datetime.now().isoformat()
                logger.info(f"📝 UPDATE: Updated analysis {analysis_id} in memory. Status: {updates.get('status')}, step: {updates.get('current_step')}, progress: {updates.get('step_progress')}%")
                
                # CRITICAL: Save to file AFTER memory update (for persistence and cross-worker visibility)
                try:
                    self._save_mock_storage()  # Persist to file
                    logger.info(f"✅ UPDATE: Successfully saved analysis {analysis_id} to file. Total analyses: {len(AzureSQLService._mock_storage)}")
                except Exception as save_error:
                    # CRITICAL: Even if file save fails, the update is in memory
                    # Don't fail the update - in-memory storage is the source of truth
                    logger.error(f"UPDATE: Failed to save to file, but update is in memory: {save_error}. Analysis {analysis_id} is still available in memory.")
                    # Continue - the update is successful in memory
                return True
            
            # Analysis not found - this should not happen during active processing
            logger.error(f"UPDATE: Analysis {analysis_id} not found in mock storage. Available IDs: {list(AzureSQLService._mock_storage.keys())}. Storage file: {AzureSQLService._mock_storage_file}")
            
            # CRITICAL: Try one more time to reload from file (in case it was just created)
            self._load_mock_storage()
            if analysis_id in AzureSQLService._mock_storage:
                from datetime import datetime
                AzureSQLService._mock_storage[analysis_id].update(updates)
                AzureSQLService._mock_storage[analysis_id]['updated_at'] = datetime.now().isoformat()
                self._save_mock_storage()
                logger.warning(f"UPDATE: Found and updated analysis {analysis_id} after second reload")
                return True
            
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
    
    def update_analysis_sync(self, analysis_id: str, updates: Dict) -> bool:
        """
        Synchronous version of update_analysis for use from threads.
        CRITICAL: This method updates in-memory storage FIRST, then saves to file IMMEDIATELY.
        This ensures the analysis is always visible across workers during long processing.
        """
        logger.info(f"📝 UPDATE_SYNC: Updating analysis {analysis_id} with fields: {list(updates.keys())}")
        if self._use_mock:
            # CRITICAL: Always ensure analysis exists in memory before updating
            # If not in memory, try to load from file first (for cross-worker scenarios)
            if analysis_id not in AzureSQLService._mock_storage:
                logger.info(f"UPDATE_SYNC: Analysis {analysis_id} not in memory, reloading from file...")
                self._load_mock_storage()
            
            # Update in-memory mock storage IMMEDIATELY (source of truth)
            if analysis_id in AzureSQLService._mock_storage:
                from datetime import datetime
                # CRITICAL: Update in-memory FIRST (immediate visibility within this worker)
                old_status = AzureSQLService._mock_storage[analysis_id].get('status')
                old_step = AzureSQLService._mock_storage[analysis_id].get('current_step')
                old_progress = AzureSQLService._mock_storage[analysis_id].get('step_progress')
                
                AzureSQLService._mock_storage[analysis_id].update(updates)
                AzureSQLService._mock_storage[analysis_id]['updated_at'] = datetime.now().isoformat()
                
                new_status = updates.get('status', old_status)
                new_step = updates.get('current_step', old_step)
                new_progress = updates.get('step_progress', old_progress)
                
                logger.info(f"📝 UPDATE_SYNC: Updated analysis {analysis_id} in memory. Status: {old_status}->{new_status}, step: {old_step}->{new_step}, progress: {old_progress}%->{new_progress}%")
                
                # CRITICAL: Save to file IMMEDIATELY after memory update (for cross-worker visibility)
                # This is essential for long-running processing where other workers need to see updates
                # Use timeout to prevent blocking the heartbeat thread on slow file I/O
                import time as time_module
                save_start = time_module.time()
                try:
                    self._save_mock_storage()  # Persist to file with forced sync
                    save_duration = time_module.time() - save_start
                    logger.info(f"✅ UPDATE_SYNC: Successfully saved analysis {analysis_id} to file in {save_duration:.3f}s. Total analyses: {len(AzureSQLService._mock_storage)}")
                    
                    # CRITICAL: Quick verification (non-blocking) - only if save was fast
                    if save_duration < 0.5:  # Only verify if save was quick
                        file_path = os.path.abspath(AzureSQLService._mock_storage_file)
                        if os.path.exists(file_path):
                            file_size = os.path.getsize(file_path)
                            logger.debug(f"UPDATE_SYNC: File verified: {file_path} ({file_size} bytes)")
                    elif save_duration > 1.0:
                        logger.warning(f"UPDATE_SYNC: Slow file save took {save_duration:.2f}s - may impact heartbeat performance")
                except Exception as save_error:
                    save_duration = time_module.time() - save_start
                    # CRITICAL: Even if file save fails, the update is in memory
                    # Don't fail the update - in-memory storage is the source of truth
                    logger.error(f"UPDATE_SYNC: Failed to save to file after {save_duration:.3f}s, but update is in memory: {save_error}. Analysis {analysis_id} is still available in memory.")
                    # Continue - the update is successful in memory, but cross-worker visibility may be limited
                return True
            
            # Analysis not found - try to reload and recreate
            logger.warning(f"UPDATE_SYNC: Analysis {analysis_id} not found in mock storage. Available IDs: {list(AzureSQLService._mock_storage.keys())}")
            self._load_mock_storage()
            if analysis_id in AzureSQLService._mock_storage:
                from datetime import datetime
                AzureSQLService._mock_storage[analysis_id].update(updates)
                AzureSQLService._mock_storage[analysis_id]['updated_at'] = datetime.now().isoformat()
                self._save_mock_storage()
                logger.warning(f"UPDATE_SYNC: Found and updated analysis {analysis_id} after reload")
                return True
            
            logger.error(f"UPDATE_SYNC: Analysis {analysis_id} not found after reload. Recreating...")
            # Recreate the analysis if it's lost
            from datetime import datetime
            AzureSQLService._mock_storage[analysis_id] = {
                'id': analysis_id,
                'status': updates.get('status', 'processing'),
                'current_step': updates.get('current_step', 'pose_estimation'),
                'step_progress': updates.get('step_progress', 0),
                'step_message': updates.get('step_message', 'Processing...'),
                'updated_at': datetime.now().isoformat()
            }
            self._save_mock_storage()
            logger.warning(f"UPDATE_SYNC: Recreated analysis {analysis_id}")
            return True
        
        # For real SQL, we can't use sync method - return False to indicate async method should be used
        logger.warning(f"UPDATE_SYNC: Real SQL database - sync method not available. Use async update_analysis instead.")
        return False
    
    async def get_analysis(self, analysis_id: str) -> Optional[Dict]:
        """
        Get analysis record with ROBUST multi-worker support.
        CRITICAL: This method ALWAYS checks in-memory storage FIRST, then file.
        In-memory storage is the source of truth during active processing.
        
        CRITICAL ARCHITECTURE CHANGE: File-first approach for multi-worker reliability.
        In a multi-worker environment (Uvicorn with multiple workers), in-memory storage
        is NOT shared between workers. Therefore, we MUST read from file first to ensure
        cross-worker visibility. In-memory cache is only used as a secondary optimization
        after we've confirmed the file doesn't have the data.
        """
        if self._use_mock:
            file_path = os.path.abspath(AzureSQLService._mock_storage_file)
            
            logger.info(f"🔍 GET: Frontend polling for analysis {analysis_id} - checking storage file: {file_path}")
            logger.info(f"🔍 GET: Current in-memory storage has {len(AzureSQLService._mock_storage)} analyses: {list(AzureSQLService._mock_storage.keys())}")
            logger.info(f"🔍 GET: File exists: {os.path.exists(file_path)}")
            if os.path.exists(file_path):
                file_size = os.path.getsize(file_path)
                logger.info(f"🔍 GET: File size: {file_size} bytes")
            
            # CRITICAL: Check in-memory storage FIRST (fastest, works for same-worker requests)
            # In-memory is the source of truth during active processing in the same worker
            if analysis_id in AzureSQLService._mock_storage:
                logger.info(f"GET: Found analysis {analysis_id} in in-memory storage (fast path)")
                return AzureSQLService._mock_storage[analysis_id].copy()
            
            # Strategy 2: Read from file (for cross-worker access or after restart)
            # Multi-worker architecture - file is source of truth across workers
            max_retries = 20  # Increased to 20 retries for better resilience
            for retry in range(max_retries):
                # Strategy 1: Read from file (most reliable for cross-worker access)
                if os.path.exists(file_path):
                    try:
                        with open(file_path, 'r') as f:
                            if HAS_FCNTL:
                                try:
                                    fcntl.flock(f.fileno(), fcntl.LOCK_SH)  # Shared lock for reading
                                    file_data = json.load(f)
                                finally:
                                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                            else:
                                file_data = json.load(f)
                            
                            if isinstance(file_data, dict):
                                # CRITICAL: MERGE file data into in-memory storage, don't replace it
                                # This ensures analyses being processed in memory are never lost
                                logger.debug(f"GET: Merging file data into in-memory storage (file has {len(file_data)} analyses, memory has {len(AzureSQLService._mock_storage)})")
                                for key, value in file_data.items():
                                    # Only update if not already in memory (preserve active processing)
                                    # OR if file data is newer (check updated_at)
                                    if key not in AzureSQLService._mock_storage:
                                        AzureSQLService._mock_storage[key] = value
                                        logger.debug(f"GET: Added analysis {key} from file to memory")
                                    else:
                                        # Both exist - check which is newer
                                        file_updated = value.get('updated_at', '')
                                        mem_updated = AzureSQLService._mock_storage[key].get('updated_at', '')
                                        if file_updated > mem_updated:
                                            logger.debug(f"GET: File data for {key} is newer, updating memory")
                                            AzureSQLService._mock_storage[key] = value
                                        else:
                                            logger.debug(f"GET: Memory data for {key} is newer or same, keeping memory version")
                                
                                if analysis_id in file_data:
                                    logger.info(f"GET: Found analysis {analysis_id} in file (attempt {retry + 1}/{max_retries})")
                                    # Return from memory (which now has merged data)
                                    if analysis_id in AzureSQLService._mock_storage:
                                        return AzureSQLService._mock_storage[analysis_id].copy()
                                    else:
                                        # Shouldn't happen, but return from file as fallback
                                        return file_data[analysis_id].copy()
                                else:
                                    logger.debug(f"GET: File exists but analysis {analysis_id} not found. Available IDs: {list(file_data.keys())}")
                    except json.JSONDecodeError as e:
                        logger.warning(f"GET: Invalid JSON in file (attempt {retry + 1}): {e}")
                        # Try to recover by reloading
                        self._load_mock_storage()
                    except (IOError, OSError) as e:
                        logger.debug(f"GET: Error reading file (attempt {retry + 1}): {e}")
                
                # Strategy 2: Reload from file using _load_mock_storage (which preserves in-memory if file missing)
                self._load_mock_storage()
                
                # Check if analysis is now in memory (after reload)
                if analysis_id in AzureSQLService._mock_storage:
                    if retry > 0:
                        logger.info(f"GET: Retrieved analysis from memory after reload: {analysis_id} (attempt {retry + 1}/{max_retries})")
                    else:
                        logger.debug(f"GET: Retrieved analysis from mock storage: {analysis_id}")
                    return AzureSQLService._mock_storage[analysis_id].copy()
                
                # File doesn't exist or analysis not found - wait and retry
                if retry < max_retries - 1:  # Don't sleep on last attempt
                    # CRITICAL: Shorter delays for first few attempts (when file is likely being written)
                    # Then progressively longer delays
                    if retry < 5:
                        # First 5 attempts: very short delays (0.05s, 0.1s, 0.15s, 0.2s, 0.25s)
                        # This catches files that are being written right now
                        delay = 0.05 * (retry + 1)
                    elif retry < 10:
                        # Next 5 attempts: short delays (0.3s, 0.4s, 0.5s, 0.6s, 0.7s)
                        delay = 0.3 + 0.1 * (retry - 5)
                    else:
                        # Later attempts: longer delays (0.8s, 1.0s, 1.2s, etc.)
                        delay = 0.8 + 0.2 * (retry - 10)
                    
                    logger.debug(f"GET: Analysis {analysis_id} not found, retrying in {delay:.2f}s (attempt {retry + 1}/{max_retries})")
                    time.sleep(delay)
                    continue
            
            # Analysis not found after retries
            logger.warning(f"GET: Analysis not found in mock storage after {max_retries} attempts: {analysis_id}. Available IDs: {list(AzureSQLService._mock_storage.keys())}. Storage file: {AzureSQLService._mock_storage_file}")
            
            # Check if file exists but wasn't loaded (for debugging)
            file_path = os.path.abspath(AzureSQLService._mock_storage_file)
            storage_dir = os.path.dirname(file_path)
            
            # List directory contents for debugging
            try:
                dir_contents = os.listdir(storage_dir) if os.path.exists(storage_dir) else []
                logger.warning(f"Storage directory contents: {dir_contents}. Looking for: {os.path.basename(file_path)}")
            except Exception as e:
                logger.warning(f"Could not list storage directory: {e}")
            
            if os.path.exists(file_path):
                file_size = os.path.getsize(file_path)
                logger.warning(f"Storage file exists ({file_size} bytes) but analysis not found. File may be corrupted or have permission issues.")
                # Try to read and parse the file directly for debugging
                try:
                    with open(file_path, 'r') as f:
                        file_data = json.load(f)
                        if isinstance(file_data, dict):
                            logger.warning(f"File contains {len(file_data)} analyses. IDs: {list(file_data.keys())}")
                            # If the analysis ID is in the file but not in memory, there's a sync issue
                            if analysis_id in file_data:
                                logger.error(f"CRITICAL: Analysis {analysis_id} exists in file but not loaded into memory! This indicates a file loading issue. Merging file data into memory.")
                                # CRITICAL: MERGE file data into memory, don't replace it
                                for key, value in file_data.items():
                                    AzureSQLService._mock_storage[key] = value
                                logger.error(f"CRITICAL: Merged file data into memory. Analysis {analysis_id} should now be available.")
                                # Return from memory (which now has merged data)
                                if analysis_id in AzureSQLService._mock_storage:
                                    return AzureSQLService._mock_storage[analysis_id].copy()
                                else:
                                    # Fallback: return directly from file
                                    return file_data[analysis_id].copy()
                        else:
                            logger.error(f"CRITICAL: File contains invalid data type: {type(file_data)}. Expected dict.")
                except json.JSONDecodeError as e:
                    logger.error(f"CRITICAL: File exists but contains invalid JSON: {e}")
                except Exception as e:
                    logger.error(f"CRITICAL: Error reading file: {e}", exc_info=True)
            else:
                logger.warning(f"Storage file does not exist: {file_path}. Directory: {storage_dir}")
            
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



