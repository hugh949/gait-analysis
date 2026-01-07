"""
Reports API endpoints
Generates reports for different audiences
"""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from typing import Optional
from loguru import logger

from app.services.reporting import ReportingService
from app.services.metrics_calculator import GaitMetrics
from app.core.database import db

router = APIRouter()
reporting_service = ReportingService()


@router.get("/{analysis_id}")
async def get_reports(
    analysis_id: str,
    audience: Optional[str] = Query(None, description="medical, caregiver, or older_adult")
):
    """
    Get reports for analysis
    
    If audience is specified, returns only that report.
    Otherwise, returns all reports.
    """
    try:
        # Retrieve analysis
        container = await db.get_container("analyses")
        analysis = container.read_item(item=analysis_id, partition_key=analysis_id)
        
        if analysis['status'] != 'completed':
            raise HTTPException(
                status_code=400,
                detail=f"Analysis not completed. Status: {analysis['status']}"
            )
        
        # Reconstruct metrics object
        metrics_dict = analysis.get('metrics', {})
        metrics = GaitMetrics(**metrics_dict)
        
        # Get previous metrics if available (for trend calculation)
        previous_metrics = None
        if 'patient_id' in analysis:
            # Query previous analyses for same patient
            query = f"SELECT * FROM c WHERE c.patient_id = '{analysis['patient_id']}' AND c.status = 'completed' AND c.id != '{analysis_id}' ORDER BY c._ts DESC OFFSET 0 LIMIT 1"
            previous_items = list(container.query_items(query=query, enable_cross_partition_query=True))
            if previous_items:
                prev_metrics_dict = previous_items[0].get('metrics', {})
                previous_metrics = GaitMetrics(**prev_metrics_dict)
        
        # Generate reports
        all_reports = reporting_service.generate_all_reports(
            metrics,
            patient_id=analysis.get('patient_id'),
            previous_metrics=previous_metrics,
            video_overlay_available=False  # Would check if overlay is available
        )
        
        # Return requested audience or all
        if audience:
            if audience not in ['medical', 'caregiver', 'older_adult']:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid audience. Must be: medical, caregiver, or older_adult"
                )
            return JSONResponse(all_reports[audience])
        
        return JSONResponse(all_reports)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating reports for {analysis_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error generating reports: {str(e)}")


@router.get("/{analysis_id}/fhir")
async def get_fhir_report(analysis_id: str):
    """Get FHIR-formatted report for EMR integration"""
    try:
        container = await db.get_container("analyses")
        analysis = container.read_item(item=analysis_id, partition_key=analysis_id)
        
        if analysis['status'] != 'completed':
            raise HTTPException(
                status_code=400,
                detail=f"Analysis not completed. Status: {analysis['status']}"
            )
        
        metrics_dict = analysis.get('metrics', {})
        metrics = GaitMetrics(**metrics_dict)
        
        # Generate FHIR report
        from app.services.reporting import MedicalReportGenerator
        medical_gen = MedicalReportGenerator()
        fhir_report = medical_gen.export_fhir(
            metrics,
            patient_id=analysis.get('patient_id', 'unknown')
        )
        
        return JSONResponse(fhir_report)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating FHIR report for {analysis_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error generating FHIR report: {str(e)}")


@router.get("/{analysis_id}/export")
async def export_report(
    analysis_id: str,
    format: str = Query("json", description="Export format: json, pdf, csv")
):
    """Export report in various formats"""
    # Implementation for PDF/CSV export would go here
    if format not in ['json']:
        raise HTTPException(
            status_code=501,
            detail=f"Export format '{format}' not yet implemented"
        )
    
    # For now, just return JSON
    return await get_reports(analysis_id, audience=None)



