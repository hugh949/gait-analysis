# Contributing to Gait Analysis Platform

## Development Setup

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt  # If available
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## Running Tests

### Backend Tests

```bash
cd backend
pytest
pytest tests/ -v  # Verbose output
pytest tests/test_metrics_calculator.py  # Specific test file
```

### Frontend Tests

```bash
cd frontend
npm test
```

## Code Style

### Python

- Follow PEP 8
- Use type hints
- Maximum line length: 100 characters
- Use Black for formatting (if configured)

### TypeScript/React

- Use TypeScript strict mode
- Follow React best practices
- Use functional components with hooks
- Maximum line length: 100 characters

## Pull Request Process

1. Create a feature branch
2. Make your changes
3. Add tests for new functionality
4. Ensure all tests pass
5. Update documentation if needed
6. Submit pull request with clear description

## Validation Requirements

All changes must maintain:
- Quality gate thresholds (≥80% confidence)
- Anatomical constraint validation
- Clinical metric accuracy
- Multi-audience report compatibility

## Clinical Considerations

When modifying metrics or reporting:
- Consult clinical validation data
- Maintain backward compatibility with existing analyses
- Update normative comparison data if needed
- Document any changes to interpretation logic



