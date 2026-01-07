# Quick Start Guide

## Local Development Setup

### 1. Backend Setup

```bash
# Navigate to backend directory
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp ../.env.example .env
# Edit .env with your Azure credentials (or use local defaults for testing)

# Run the server
python main.py
```

The API will be available at `http://localhost:8000`

### 2. Frontend Setup

```bash
# Navigate to frontend directory
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev
```

The frontend will be available at `http://localhost:3000`

### 3. Test the Application

1. Open `http://localhost:3000` in your browser
2. Navigate to "Upload Video"
3. Upload a video file (MP4, AVI, MOV, or MKV)
4. Wait for analysis to complete
5. View results in the appropriate dashboard:
   - Medical: Technical details
   - Caregiver: Fall risk and trends
   - Older Adult: Simple health score

## API Endpoints

### Health Check
```
GET /health
```

### Upload Video
```
POST /api/v1/analysis/upload
Content-Type: multipart/form-data

Parameters:
- file: Video file
- patient_id: (optional) Patient identifier
- view_type: (optional) front, side, or diagonal
- reference_length_mm: (optional) Reference object length
- fps: (optional) Video frame rate
```

### Get Analysis
```
GET /api/v1/analysis/{analysis_id}
```

### Get Reports
```
GET /api/v1/reports/{analysis_id}?audience={medical|caregiver|older_adult}
```

## Testing

### Backend Tests

```bash
cd backend
pytest
```

### Frontend Tests

```bash
cd frontend
npm test  # If test suite is configured
```

## Next Steps

1. **Configure Azure Services**: See `DEPLOYMENT.md` for Azure setup
2. **Train/Download Models**: 
   - Pose estimation model (HRNet/ViTPose)
   - 3D lifting model
   - SMPL-X body model
3. **Validate Against Gold Standard**: Set up synchronized trials with IR-marker systems
4. **Deploy to Production**: Follow deployment guide

## Troubleshooting

### Backend Issues

- **Import errors**: Ensure virtual environment is activated
- **Database connection**: Check Azure Cosmos DB credentials in `.env`
- **Model loading**: Ensure model files are in correct paths

### Frontend Issues

- **API connection**: Check `VITE_API_URL` in frontend environment
- **Build errors**: Clear `node_modules` and reinstall
- **CORS errors**: Ensure backend CORS settings include frontend URL

### Video Processing Issues

- **File too large**: Check `MAX_VIDEO_SIZE_MB` setting
- **Unsupported format**: Ensure video is in supported format
- **Processing timeout**: Increase timeout or use background processing

## Development Tips

1. **Use background tasks** for video processing to avoid timeouts
2. **Cache models** in memory after first load
3. **Monitor quality gates** to catch issues early
4. **Log extensively** for debugging production issues
5. **Test with real videos** from target population

## Support

For issues or questions:
- Check `ARCHITECTURE.md` for system design
- Review `DEPLOYMENT.md` for deployment issues
- See `CONTRIBUTING.md` for development guidelines



