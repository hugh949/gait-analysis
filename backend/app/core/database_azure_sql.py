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
import threading
import asyncio

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
    
    # File watcher thread for automatic reloading in multi-worker environment
    _file_watcher_thread: Optional[threading.Thread] = None
    _file_watcher_stop_event: Optional[threading.Event] = None
    _last_file_mtime: float = 0.0
    
    def __init__(self):
        """Initialize database connection - tries Table Storage first, then SQL, then mock"""
        # Priority 1: Try Azure Table Storage (cheap, reliable, uses existing storage account)
        storage_conn = os.getenv(
            "AZURE_STORAGE_CONNECTION_STRING",
            getattr(settings, "AZURE_STORAGE_CONNECTION_STRING", None) if settings else None
        )
        
        if storage_conn:
            try:
                from azure.data.tables import TableServiceClient
                table_service = TableServiceClient.from_connection_string(storage_conn)
                self.table_name = "gaitanalyses"
                table_service.create_table_if_not_exists(table_name=self.table_name)
                self.table_client = table_service.get_table_client(table_name=self.table_name)
                self._use_table = True
                self._use_mock = False
                self.connection_string = None
                logger.info(f"✅ Using Azure Table Storage: table '{self.table_name}'")
                return
            except Exception as e:
                logger.warning(f"Failed to initialize Table Storage: {e}, falling back to SQL/mock")
        
        # Priority 2: Try Azure SQL Database
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
        
        if all([self.server, self.username, self.password]):
            self._use_mock = False
            self._use_table = False
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
            logger.info(f"✅ Using Azure SQL Database: {self.server}/{self.database}")
            # Initialize database schema
            self._init_schema()
            return
        
        # Priority 3: Fallback to file-based mock storage (unreliable in multi-worker)
        logger.warning("⚠️  No database configured - using file-based mock storage (unreliable in multi-worker environments)")
        logger.warning("⚠️  RECOMMENDED: Configure Azure Table Storage or SQL Database for reliability")
        self.connection_string = None
        self._use_mock = True
        self._use_table = False
        # Ensure class variable exists (in case it was cleared)
        if not hasattr(AzureSQLService, '_mock_storage') or AzureSQLService._mock_storage is None:
            AzureSQLService._mock_storage = {}
        # Load from file if it exists (persist across restarts)
        self._load_mock_storage()
    
    def _start_file_watcher(self):
        """Start a background thread that watches the storage file and reloads it when it changes"""
        if AzureSQLService._file_watcher_thread is not None and AzureSQLService._file_watcher_thread.is_alive():
            return  # Already running
        
        if AzureSQLService._file_watcher_stop_event is None:
            AzureSQLService._file_watcher_stop_event = threading.Event()
        
        # Initialize last file mtime
        if os.path.exists(AzureSQLService._mock_storage_file):
            AzureSQLService._last_file_mtime = os.path.getmtime(AzureSQLService._mock_storage_file)
        
        def file_watcher():
            """Background thread that periodically checks if storage file has changed and reloads it"""
            logger.info("📁 FILE WATCHER: Starting file watcher thread for multi-worker synchronization")
            while not AzureSQLService._file_watcher_stop_event.is_set():
                try:
                    if os.path.exists(AzureSQLService._mock_storage_file):
                        current_mtime = os.path.getmtime(AzureSQLService._mock_storage_file)
                        if current_mtime > AzureSQLService._last_file_mtime:
                            logger.debug(f"📁 FILE WATCHER: Storage file changed (mtime: {current_mtime}), reloading...")
                            AzureSQLService._last_file_mtime = current_mtime
                            # STABILITY MODE: Add small delay before reload to ensure file write is complete
                            # This reduces race condition where file watcher reads during heartbeat save
                            time.sleep(0.1)  # 100ms delay to let file write complete
                            # Reload from file (this merges with in-memory, preserving active processing)
                            # File locking in _load_mock_storage will prevent reading during writes
                            self._load_mock_storage()
                    else:
                        # File doesn't exist yet - check again later
                        pass
                except Exception as e:
                    logger.warning(f"📁 FILE WATCHER: Error checking file: {e}")
                
                # STABILITY MODE: Check every 2.0 seconds to reduce race condition window
                # This reduces the chance of file watcher reloading while heartbeat is saving
                # Still fast enough for cross-worker synchronization (2s is acceptable)
                AzureSQLService._file_watcher_stop_event.wait(2.0)
            
            logger.info("📁 FILE WATCHER: File watcher thread stopped")
        
        AzureSQLService._file_watcher_thread = threading.Thread(target=file_watcher, daemon=True, name="mock-storage-watcher")
        AzureSQLService._file_watcher_thread.start()
        logger.info("📁 FILE WATCHER: File watcher thread started")
    
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
            
            # CRITICAL: Verify temp file has content before renaming
            temp_file_size = os.path.getsize(temp_file)
            if temp_file_size == 0:
                logger.error(f"SAVE: Temp file is empty (0 bytes): {temp_file}")
                os.unlink(temp_file)  # Remove empty temp file
                raise ValueError(f"Temp file is empty: {temp_file}")
            
            logger.info(f"SAVE: Temp file size: {temp_file_size} bytes, contains {len(AzureSQLService._mock_storage)} analyses")
            
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
            
            # STABILITY MODE: Increased delay for filesystem visibility
            # Increased to 50ms to ensure file is fully synced before next operation
            # This is critical for multi-worker scenarios where file visibility is essential
            time.sleep(0.05)  # 50ms delay - ensures filesystem sync completes
            
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
        # Priority 1: Use Table Storage if available
        if hasattr(self, '_use_table') and self._use_table:
            try:
                from datetime import datetime
                analysis_id = analysis_data.get('id')
                if not analysis_id:
                    logger.error("Analysis data missing 'id' field")
                    return False
                
                entity = {
                    'PartitionKey': 'analyses',
                    'RowKey': analysis_id,
                    'patient_id': analysis_data.get('patient_id'),
                    'filename': analysis_data.get('filename', ''),
                    'video_url': analysis_data.get('video_url'),
                    'status': analysis_data.get('status', 'processing'),
                    'current_step': analysis_data.get('current_step', 'pose_estimation'),
                    'step_progress': analysis_data.get('step_progress', 0),
                    'step_message': analysis_data.get('step_message', 'Initializing...'),
                    'metrics': json.dumps(analysis_data.get('metrics', {})),
                    'created_at': datetime.utcnow().isoformat(),
                    'updated_at': datetime.utcnow().isoformat()
                }
                
                self.table_client.create_entity(entity=entity)
                logger.info(f"✅ Created analysis {analysis_id} in Table Storage")
                
                # CRITICAL: Verify the entity was actually created and is immediately readable
                # Table Storage can have eventual consistency, so we verify with retries
                verification_passed = False
                max_verify_attempts = 5
                for verify_attempt in range(max_verify_attempts):
                    try:
                        await asyncio.sleep(0.1 * (verify_attempt + 1))  # Progressive delay: 0.1s, 0.2s, 0.3s, 0.4s, 0.5s
                        verify_entity = self.table_client.get_entity(
                            partition_key='analyses',
                            row_key=analysis_id
                        )
                        if verify_entity and verify_entity.get('RowKey') == analysis_id:
                            verification_passed = True
                            logger.info(f"✅ Verified analysis {analysis_id} is readable in Table Storage (attempt {verify_attempt + 1})")
                            break
                    except Exception as verify_error:
                        if verify_attempt < max_verify_attempts - 1:
                            logger.debug(f"Verification attempt {verify_attempt + 1} failed, retrying: {verify_error}")
                        else:
                            logger.warning(f"Could not verify analysis in Table Storage after {max_verify_attempts} attempts: {verify_error}")
                
                if not verification_passed:
                    logger.warning(f"Analysis {analysis_id} created in Table Storage but verification failed - may have eventual consistency delay")
                    # Still return True because creation succeeded, just verification had issues
                
                return True
            except Exception as e:
                logger.error(f"Failed to create analysis in Table Storage: {e}", exc_info=True)
                return False
        
        if self._use_mock:
            # CRITICAL: Reload from file first to ensure we don't overwrite existing data
            self._load_mock_storage()
            
            # Store in in-memory mock storage (use class variable to ensure persistence)
            from datetime import datetime
            analysis_id = analysis_data.get('id')
            if not analysis_id:
                logger.error("Analysis data missing 'id' field")
                return False
            
            # CRITICAL: Store in in-memory storage FIRST (source of truth)
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
            
            logger.error(f"💾💾💾 CREATE: Stored analysis {analysis_id} in MEMORY FIRST 💾💾💾")
            logger.error(f"💾 In-memory storage size: {len(AzureSQLService._mock_storage)}")
            logger.error(f"💾 In-memory analysis IDs: {list(AzureSQLService._mock_storage.keys())}")
            logger.error(f"💾 Analysis in memory: {analysis_id in AzureSQLService._mock_storage}")
            
            logger.info(f"💾 CREATE: About to save mock storage with {len(AzureSQLService._mock_storage)} analyses. Analysis ID: {analysis_id}")
            self._save_mock_storage()  # Persist to file
            logger.info(f"💾 CREATE: Saved analysis {analysis_id} to file. In-memory storage now has: {list(AzureSQLService._mock_storage.keys())}")
            
            # CRITICAL: Verify it's still in memory after save
            if analysis_id not in AzureSQLService._mock_storage:
                logger.error(f"💾❌❌❌ CRITICAL: Analysis disappeared from memory after save! ❌❌❌")
                logger.error(f"💾 Re-adding to memory...")
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
                logger.error(f"💾✅ Re-added analysis to memory")
            
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
                logger.error(f"CREATE: ❌❌❌ CRITICAL: Analysis {analysis_id} created but could not be verified in file ❌❌❌")
                logger.error(f"CREATE: 🔍🔍🔍 DIAGNOSTIC: File verification failure 🔍🔍🔍")
                logger.error(f"CREATE: 🔍   - Analysis ID: {analysis_id}")
                logger.error(f"CREATE: 🔍   - In-memory: {analysis_id in AzureSQLService._mock_storage}")
                logger.error(f"CREATE: 🔍   - File path: {file_path}")
                logger.error(f"CREATE: 🔍   - File exists: {os.path.exists(file_path)}")
                if os.path.exists(file_path):
                    try:
                        with open(file_path, 'r') as f:
                            if HAS_FCNTL:
                                fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                                try:
                                    file_data = json.load(f)
                                    logger.error(f"CREATE: 🔍   - File has {len(file_data)} analyses")
                                    logger.error(f"CREATE: 🔍   - Analysis in file: {analysis_id in file_data}")
                                    if analysis_id not in file_data:
                                        logger.error(f"CREATE: 🔍   - File analysis IDs: {list(file_data.keys())[:10]}")
                                finally:
                                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                            else:
                                file_data = json.load(f)
                                logger.error(f"CREATE: 🔍   - File has {len(file_data)} analyses")
                                logger.error(f"CREATE: 🔍   - Analysis in file: {analysis_id in file_data}")
                                if analysis_id not in file_data:
                                    logger.error(f"CREATE: 🔍   - File analysis IDs: {list(file_data.keys())[:10]}")
                    except Exception as read_error:
                        logger.error(f"CREATE: 🔍   - Could not read file: {read_error}")
                
                # CRITICAL: Try one more save attempt with force sync
                logger.warning(f"CREATE: ⚠️ Attempting final save with force sync...")
                try:
                    self._save_mock_storage(force_sync=True)
                    time.sleep(0.5)  # Wait for sync
                    # Check again
                    if os.path.exists(file_path):
                        with open(file_path, 'r') as f:
                            if HAS_FCNTL:
                                fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                                try:
                                    verify_data = json.load(f)
                                    if isinstance(verify_data, dict) and analysis_id in verify_data:
                                        verification_passed = True
                                        logger.info(f"CREATE: ✅ Final verification passed after force sync")
                                finally:
                                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                            else:
                                verify_data = json.load(f)
                                if isinstance(verify_data, dict) and analysis_id in verify_data:
                                    verification_passed = True
                                    logger.info(f"CREATE: ✅ Final verification passed after force sync")
                except Exception as final_save_error:
                    logger.error(f"CREATE: ❌ Final save attempt failed: {final_save_error}", exc_info=True)
                
                if not verification_passed:
                    # CRITICAL: Analysis exists in memory but not in file - this will cause "Analysis not found" errors
                    # Return False to indicate creation failed, so upload endpoint can retry or fail gracefully
                    logger.error(f"CREATE: ❌❌❌ RETURNING FALSE: Analysis not verifiable in file ❌❌❌")
                    return False
                
                # If we got here, verification passed on retry
                logger.info(f"CREATE: ✅ Analysis verified after retry")
            
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
        Update analysis record
        """
        # Priority 1: Use Table Storage if available
        if hasattr(self, '_use_table') and self._use_table:
            try:
                from azure.core.exceptions import ResourceNotFoundError
                from datetime import datetime
                
                # Get existing entity
                entity = self.table_client.get_entity(
                    partition_key='analyses',
                    row_key=analysis_id
                )
                
                # Update fields
                for key, value in updates.items():
                    if key in ['status', 'current_step', 'step_progress', 'step_message', 'video_url']:
                        entity[key] = value
                    elif key == 'metrics':
                        entity['metrics'] = json.dumps(value)
                    elif key == 'steps_completed':
                        entity['steps_completed'] = json.dumps(value)  # Store as JSON string
                
                entity['updated_at'] = datetime.utcnow().isoformat()
                
                # Update entity
                self.table_client.update_entity(entity=entity)
                logger.debug(f"✅ Updated analysis {analysis_id} in Table Storage")
                return True
            except ResourceNotFoundError:
                logger.warning(f"Analysis {analysis_id} not found in Table Storage for update")
                return False
            except Exception as e:
                logger.error(f"Failed to update analysis in Table Storage: {e}", exc_info=True)
                return False
        
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
                # Handle steps_completed specially - merge with existing if present
                if 'steps_completed' in updates:
                    existing_steps = AzureSQLService._mock_storage[analysis_id].get('steps_completed', {})
                    if isinstance(existing_steps, dict) and isinstance(updates['steps_completed'], dict):
                        existing_steps.update(updates['steps_completed'])
                        updates['steps_completed'] = existing_steps
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
                    if key in ['status', 'current_step', 'step_progress', 'step_message', 'metrics', 'video_url', 'steps_completed']:
                        set_clauses.append(f"{key} = ?")
                        if key == 'metrics' and isinstance(value, dict):
                            values.append(json.dumps(value))
                        elif key == 'steps_completed' and isinstance(value, dict):
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
            logger.error(f"Failed to update analysis {analysis_id}: {e}", exc_info=True)
            logger.error(f"Update data: {updates}")
            return False
    
    def update_analysis_sync(self, analysis_id: str, updates: Dict) -> bool:
        """
        Synchronous version of update_analysis for use from threads (e.g., heartbeat).
        For Table Storage, we use asyncio.run() to call the async method.
        """
        # Priority 1: Use Table Storage if available (via async wrapper)
        if hasattr(self, '_use_table') and self._use_table:
            try:
                import asyncio
                # For sync operations, run async update in a new event loop
                # This is safe because we're in a thread (heartbeat thread)
                try:
                    # Try to get existing loop
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # Loop is running - create new one in thread
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                except RuntimeError:
                    # No loop exists - create new one
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                
                result = loop.run_until_complete(self.update_analysis(analysis_id, updates))
                return result
            except Exception as e:
                logger.error(f"Failed to update analysis in Table Storage (sync): {e}", exc_info=True)
                return False
        
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
                
                # Only log every 10 updates to reduce log spam
                if not hasattr(AzureSQLService, '_update_count'):
                    AzureSQLService._update_count = {}
                AzureSQLService._update_count[analysis_id] = AzureSQLService._update_count.get(analysis_id, 0) + 1
                if AzureSQLService._update_count[analysis_id] % 10 == 0:
                    logger.info(f"📝 UPDATE_SYNC: Updated analysis {analysis_id} in memory (#{AzureSQLService._update_count[analysis_id]}). Status: {old_status}->{new_status}, step: {old_step}->{new_step}, progress: {old_progress}%->{new_progress}%")
                
                # OPTIMIZED: Batch file writes - only save every 1 second instead of every 0.1s
                # This reduces file I/O overhead while still ensuring frequent persistence
                current_time = time.time()
                if not hasattr(AzureSQLService, '_last_file_save'):
                    AzureSQLService._last_file_save = {}
                
                last_save_time = AzureSQLService._last_file_save.get(analysis_id, 0)
                time_since_last_save = current_time - last_save_time
                
                # Save to file every 1 second (instead of every 0.1s)
                # This reduces file I/O by 10x while still ensuring frequent persistence
                if time_since_last_save >= 1.0:
                    save_start = time.time()
                    try:
                        # Save to file with forced sync for cross-worker visibility
                        self._save_mock_storage(force_sync=True)
                        save_duration = time.time() - save_start
                        AzureSQLService._last_file_save[analysis_id] = current_time
                        
                        if save_duration > 0.1:
                            logger.warning(f"UPDATE_SYNC: File save took {save_duration:.3f}s (may impact heartbeat)")
                        elif AzureSQLService._update_count[analysis_id] % 20 == 0:  # Log every 20 saves
                            logger.debug(f"✅ UPDATE_SYNC: Saved analysis {analysis_id} to file in {save_duration:.3f}s")
                    except Exception as save_error:
                        save_duration = time.time() - save_start
                        # CRITICAL: Even if file save fails, the update is in memory
                        logger.error(f"UPDATE_SYNC: Failed to save to file after {save_duration:.3f}s, but update is in memory: {save_error}")
                        # Continue - the update is successful in memory
                
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
        Get analysis record - uses Table Storage, SQL, or mock storage based on configuration
        """
        # Priority 1: Use Table Storage if available (most reliable)
        if hasattr(self, '_use_table') and self._use_table:
            # CRITICAL: Add retry logic for Table Storage to handle eventual consistency
            # Table Storage can have slight delays, especially after creation
            max_retries = 5
            last_error = None
            
            for retry in range(max_retries):
                try:
                    from azure.core.exceptions import ResourceNotFoundError
                    import asyncio
                    
                    # Add small delay for retries (except first attempt)
                    if retry > 0:
                        await asyncio.sleep(0.2 * retry)  # Progressive delay: 0.2s, 0.4s, 0.6s, 0.8s
                    
                    entity = self.table_client.get_entity(
                        partition_key='analyses',
                        row_key=analysis_id
                    )
                    
                    analysis = {
                        'id': entity.get('RowKey'),
                        'patient_id': entity.get('patient_id'),
                        'filename': entity.get('filename'),
                        'video_url': entity.get('video_url'),
                        'status': entity.get('status'),
                        'current_step': entity.get('current_step'),
                        'step_progress': entity.get('step_progress', 0),
                        'step_message': entity.get('step_message'),
                        'metrics': json.loads(entity.get('metrics', '{}')) if isinstance(entity.get('metrics'), str) else entity.get('metrics', {}),
                        'steps_completed': json.loads(entity.get('steps_completed', '{}')) if isinstance(entity.get('steps_completed'), str) else entity.get('steps_completed', {}),
                        'created_at': entity.get('created_at'),
                        'updated_at': entity.get('updated_at')
                    }
                    logger.debug(f"✅ Retrieved analysis {analysis_id} from Table Storage (attempt {retry + 1})")
                    return analysis
                except ResourceNotFoundError:
                    if retry < max_retries - 1:
                        logger.debug(f"Analysis {analysis_id} not found in Table Storage (attempt {retry + 1}/{max_retries}), retrying...")
                        last_error = "ResourceNotFoundError"
                        continue
                    else:
                        logger.debug(f"Analysis {analysis_id} not found in Table Storage after {max_retries} attempts")
                        return None
                except Exception as e:
                    last_error = str(e)
                    if retry < max_retries - 1:
                        logger.warning(f"Failed to get analysis from Table Storage (attempt {retry + 1}/{max_retries}): {e}, retrying...")
                        continue
                    else:
                        logger.error(f"Failed to get analysis from Table Storage after {max_retries} attempts: {e}", exc_info=True)
                        return None
            
            # Should not reach here, but just in case
            logger.error(f"Failed to get analysis {analysis_id} from Table Storage: {last_error}")
            return None
        
        if self._use_mock:
            import os
            import threading
            import time as time_module
            
            # DIAGNOSTIC: Get process/thread info for debugging multi-worker issues
            process_id = os.getpid()
            thread_id = threading.current_thread().ident
            thread_name = threading.current_thread().name
            timestamp = time_module.time()
            
            file_path = os.path.abspath(AzureSQLService._mock_storage_file)
            file_exists = os.path.exists(file_path)
            file_size = os.path.getsize(file_path) if file_exists else 0
            file_mtime = os.path.getmtime(file_path) if file_exists else 0
            file_age = timestamp - file_mtime if file_exists else 0
            
            # DIAGNOSTIC: Comprehensive state logging
            logger.error(f"🔍🔍🔍 DIAGNOSTIC GET_ANALYSIS START 🔍🔍🔍")
            logger.error(f"🔍 Analysis ID: {analysis_id}")
            logger.error(f"🔍 Process ID: {process_id}, Thread ID: {thread_id}, Thread Name: {thread_name}")
            logger.error(f"🔍 Timestamp: {timestamp:.6f}")
            logger.error(f"🔍 In-memory storage size: {len(AzureSQLService._mock_storage)}")
            logger.error(f"🔍 In-memory analysis IDs: {list(AzureSQLService._mock_storage.keys())}")
            logger.error(f"🔍 Analysis in memory: {analysis_id in AzureSQLService._mock_storage}")
            logger.error(f"🔍 File path: {file_path}")
            logger.error(f"🔍 File exists: {file_exists}")
            logger.error(f"🔍 File size: {file_size} bytes")
            logger.error(f"🔍 File age: {file_age:.3f}s")
            
            # If analysis is in memory, log its state
            if analysis_id in AzureSQLService._mock_storage:
                analysis_state = AzureSQLService._mock_storage[analysis_id]
                logger.error(f"🔍 In-memory analysis state:")
                logger.error(f"🔍   Status: {analysis_state.get('status')}")
                logger.error(f"🔍   Step: {analysis_state.get('current_step')}")
                logger.error(f"🔍   Progress: {analysis_state.get('step_progress')}%")
                logger.error(f"🔍   Updated at: {analysis_state.get('updated_at')}")
                logger.error(f"🔍   Created at: {analysis_state.get('created_at')}")
            
            # CRITICAL: Check IN-MEMORY storage FIRST (it's the source of truth during active processing)
            # The heartbeat thread updates in-memory storage immediately, so it's always up-to-date
            # Only fall back to file if not in memory (for cross-worker visibility)
            max_retries = 30  # Increased to 30 retries for better resilience
            for retry in range(max_retries):
                # Strategy 1: Check in-memory storage FIRST (fastest and most up-to-date)
                if analysis_id in AzureSQLService._mock_storage:
                    analysis_data = AzureSQLService._mock_storage[analysis_id].copy()
                    # Ensure steps_completed exists (default to empty dict if missing)
                    if 'steps_completed' not in analysis_data:
                        analysis_data['steps_completed'] = {}
                    logger.error(f"🔍✅ FOUND in MEMORY (attempt {retry + 1}/{max_retries})")
                    logger.error(f"🔍 Analysis state: status={analysis_data.get('status')}, step={analysis_data.get('current_step')}, progress={analysis_data.get('step_progress')}%")
                    logger.error(f"🔍🔍🔍 DIAGNOSTIC GET_ANALYSIS END (SUCCESS - MEMORY) 🔍🔍🔍")
                    return analysis_data
                
                # Strategy 2: Read from file (for cross-worker visibility)
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
                                    logger.error(f"🔍✅ FOUND in file (attempt {retry + 1}/{max_retries})")
                                    # CRITICAL: Merge file data into memory (preserve active processing)
                                    # But file data takes precedence for cross-worker visibility
                                    if analysis_id in AzureSQLService._mock_storage:
                                        # Both exist - check which is newer
                                        file_updated = file_data[analysis_id].get('updated_at', '')
                                        mem_updated = AzureSQLService._mock_storage[analysis_id].get('updated_at', '')
                                        if file_updated > mem_updated:
                                            # File is newer - use file data
                                            logger.error(f"🔍 File data is newer, using file version")
                                            AzureSQLService._mock_storage[analysis_id] = file_data[analysis_id]
                                        else:
                                            # Memory is newer - keep memory but merge file fields
                                            logger.error(f"🔍 Memory data is newer, keeping memory version")
                                    else:
                                        # Not in memory - add from file
                                        AzureSQLService._mock_storage[analysis_id] = file_data[analysis_id]
                                    
                                    # Return from memory (which now has the correct data)
                                    analysis_data = AzureSQLService._mock_storage[analysis_id].copy()
                                    # Ensure steps_completed exists
                                    if 'steps_completed' not in analysis_data:
                                        analysis_data['steps_completed'] = {}
                                    logger.error(f"🔍 Analysis state: status={analysis_data.get('status')}, step={analysis_data.get('current_step')}, progress={analysis_data.get('step_progress')}%")
                                    logger.error(f"🔍🔍🔍 DIAGNOSTIC GET_ANALYSIS END (SUCCESS - FILE) 🔍🔍🔍")
                                    return analysis_data
                                else:
                                    logger.debug(f"GET: File exists but analysis {analysis_id} not found. Available IDs: {list(file_data.keys())}")
                    except json.JSONDecodeError as e:
                        logger.warning(f"GET: Invalid JSON in file (attempt {retry + 1}): {e}")
                        # Try to recover by reloading
                        self._load_mock_storage()
                    except (IOError, OSError) as e:
                        logger.debug(f"GET: Error reading file (attempt {retry + 1}): {e}")
                
                # Strategy 3: Reload from file using _load_mock_storage (which preserves in-memory if file missing)
                self._load_mock_storage()
                
                # Check if analysis is now in memory (after reload)
                if analysis_id in AzureSQLService._mock_storage:
                    if retry > 0:
                        logger.info(f"GET: Retrieved analysis from memory after reload: {analysis_id} (attempt {retry + 1}/{max_retries})")
                    else:
                        logger.debug(f"GET: Retrieved analysis from mock storage: {analysis_id}")
                    analysis_data = AzureSQLService._mock_storage[analysis_id].copy()
                    # Ensure steps_completed exists
                    if 'steps_completed' not in analysis_data:
                        analysis_data['steps_completed'] = {}
                    logger.error(f"🔍✅ FOUND in MEMORY after reload (attempt {retry + 1}/{max_retries})")
                    logger.error(f"🔍 Analysis state: status={analysis_data.get('status')}, step={analysis_data.get('current_step')}, progress={analysis_data.get('step_progress')}%")
                    logger.error(f"🔍🔍🔍 DIAGNOSTIC GET_ANALYSIS END (SUCCESS - MEMORY AFTER RELOAD) 🔍🔍🔍")
                    return analysis_data
                
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
            logger.error(f"🔍❌❌❌ ANALYSIS NOT FOUND AFTER {max_retries} RETRIES ❌❌❌")
            logger.error(f"🔍 Analysis ID: {analysis_id}")
            logger.error(f"🔍 Process ID: {process_id}, Thread ID: {thread_id}, Thread Name: {thread_name}")
            logger.error(f"🔍 In-memory storage size: {len(AzureSQLService._mock_storage)}")
            logger.error(f"🔍 In-memory analysis IDs: {list(AzureSQLService._mock_storage.keys())}")
            logger.error(f"🔍 File path: {file_path}")
            logger.error(f"🔍 File exists: {os.path.exists(file_path)}")
            logger.error(f"🔍 File size: {os.path.getsize(file_path) if os.path.exists(file_path) else 0} bytes")
            logger.error(f"🔍 Storage file: {AzureSQLService._mock_storage_file}")
            
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
                                    analysis_data = AzureSQLService._mock_storage[analysis_id].copy()
                                    if 'steps_completed' not in analysis_data:
                                        analysis_data['steps_completed'] = {}
                                    return analysis_data
                                else:
                                    # Fallback: return directly from file
                                    analysis_data = file_data[analysis_id].copy()
                                    if 'steps_completed' not in analysis_data:
                                        analysis_data['steps_completed'] = {}
                                    return analysis_data
                        else:
                            logger.error(f"CRITICAL: File contains invalid data type: {type(file_data)}. Expected dict.")
                except json.JSONDecodeError as e:
                    logger.error(f"CRITICAL: File exists but contains invalid JSON: {e}")
                except Exception as e:
                    logger.error(f"CRITICAL: Error reading file: {e}", exc_info=True)
            else:
                logger.error(f"🔍 Storage file does not exist: {file_path}. Directory: {storage_dir}")
            
            logger.error(f"🔍🔍🔍 DIAGNOSTIC GET_ANALYSIS END (FAILED - NOT FOUND) 🔍🔍🔍")
            return None
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, patient_id, filename, video_url, status, 
                           current_step, step_progress, step_message, 
                           metrics, created_at, updated_at,
                           COALESCE(steps_completed, '{}') as steps_completed
                    FROM analyses
                    WHERE id = ?
                """, (analysis_id,))
                
                row = cursor.fetchone()
                if row:
                    metrics = json.loads(row[8]) if row[8] else {}
                    steps_completed = json.loads(row[11]) if len(row) > 11 and row[11] else {}
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
                        'steps_completed': steps_completed,
                        'created_at': str(row[9]),
                        'updated_at': str(row[10])
                    }
                return None
        except Exception as e:
            logger.error(f"Failed to get analysis: {e}")
            return None
    
    async def list_analyses(self, limit: int = 50) -> List[Dict]:
        """List all analyses, ordered by most recent first"""
        # Priority 1: Use Table Storage if available
        if hasattr(self, '_use_table') and self._use_table:
            try:
                entities = self.table_client.query_entities(
                    query_filter="PartitionKey eq 'analyses'"
                )
                
                analyses = []
                for entity in entities:
                    analysis = {
                        'id': entity.get('RowKey'),
                        'patient_id': entity.get('patient_id'),
                        'filename': entity.get('filename'),
                        'video_url': entity.get('video_url'),
                        'status': entity.get('status'),
                        'current_step': entity.get('current_step'),
                        'step_progress': entity.get('step_progress', 0),
                        'step_message': entity.get('step_message'),
                        'metrics': json.loads(entity.get('metrics', '{}')) if isinstance(entity.get('metrics'), str) else entity.get('metrics', {}),
                        'steps_completed': json.loads(entity.get('steps_completed', '{}')) if isinstance(entity.get('steps_completed'), str) else entity.get('steps_completed', {}),
                        'created_at': entity.get('created_at'),
                        'updated_at': entity.get('updated_at')
                    }
                    analyses.append(analysis)
                
                # Sort by updated_at descending (most recent first)
                analyses.sort(key=lambda x: x.get('updated_at', ''), reverse=True)
                logger.debug(f"✅ Listed {len(analyses[:limit])} analyses from Table Storage")
                return analyses[:limit]
            except Exception as e:
                logger.error(f"Failed to list analyses from Table Storage: {e}", exc_info=True)
                return []
        
        if self._use_mock:
            # Reload from file to ensure we have latest data
            self._load_mock_storage()
            # Get all from in-memory mock storage (use class variable to ensure persistence)
            analyses = []
            for analysis in AzureSQLService._mock_storage.values():
                analysis_copy = analysis.copy()
                # Ensure steps_completed exists (default to empty dict if missing)
                if 'steps_completed' not in analysis_copy:
                    analysis_copy['steps_completed'] = {}
                analyses.append(analysis_copy)
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



