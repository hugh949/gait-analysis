"""
Multi-Audience Reporting System
Generates reports for medical professionals, caregivers, and older adults
"""
from typing import Dict, List, Optional
from datetime import datetime
from dataclasses import asdict
import json
from loguru import logger

from app.services.metrics_calculator import GaitMetrics
from fhir.resources.observation import Observation
from fhir.resources.patient import Patient


class MedicalReportGenerator:
    """
    Technical dossier for medical professionals
    Includes biomechanical tabulations, confidence metrics, and EMR integration
    """
    
    def generate_report(
        self,
        metrics: GaitMetrics,
        keypoints_3d: Optional[any] = None,
        patient_id: Optional[str] = None,
        analysis_date: Optional[datetime] = None
    ) -> Dict:
        """Generate comprehensive medical report"""
        
        analysis_date = analysis_date or datetime.now()
        
        report = {
            'report_type': 'medical',
            'generated_at': analysis_date.isoformat(),
            'patient_id': patient_id,
            
            # Biomechanical Tabulations
            'biomechanical_parameters': {
                'spatiotemporal': {
                    'gait_speed_mm_per_s': metrics.gait_speed_mm_per_s,
                    'gait_speed_m_per_s': metrics.gait_speed_mm_per_s / 1000.0,
                    'stride_length_mm': metrics.stride_length_mm,
                    'stride_length_cm': metrics.stride_length_mm / 10.0,
                    'cadence_steps_per_min': metrics.cadence_steps_per_min,
                    'step_length_mm': metrics.step_length_mm,
                    'step_asymmetry_percent': metrics.step_asymmetry_percent
                },
                'temporal': {
                    'stance_phase_percent': metrics.stance_phase_percent,
                    'swing_phase_percent': metrics.swing_phase_percent,
                    'double_support_time_percent': metrics.double_support_time_percent,
                    'single_support_time_percent': metrics.single_support_time_percent
                },
                'joint_kinematics': {
                    'knee_flexion_peak_deg': metrics.knee_flexion_peak_deg,
                    'hip_flexion_peak_deg': metrics.hip_flexion_peak_deg,
                    'ankle_dorsiflexion_peak_deg': metrics.ankle_dorsiflexion_peak_deg,
                    'knee_clearance_mm': metrics.knee_clearance_mm,
                    'toe_clearance_mm': metrics.toe_clearance_mm
                }
            },
            
            # Z-scores against age-matched normative data
            'normative_comparison': self._calculate_z_scores(metrics),
            
            # Confidence Metrics
            'confidence_metrics': {
                'overall_confidence': metrics.overall_confidence,
                'data_quality_flags': metrics.data_quality_flags,
                'uncertainty_bounds': self._estimate_uncertainty(metrics)
            },
            
            # Clinical Interpretation
            'clinical_interpretation': self._generate_clinical_interpretation(metrics)
        }
        
        return report
    
    def _calculate_z_scores(self, metrics: GaitMetrics) -> Dict:
        """Calculate z-scores against age-matched normative data"""
        # Placeholder - would use actual normative databases
        # Typical values for older adults (65+ years)
        normative = {
            'gait_speed_m_per_s': 1.0,  # Typical older adult
            'stride_length_cm': 120.0,
            'cadence_steps_per_min': 110.0,
            'double_support_percent': 25.0
        }
        
        z_scores = {}
        if normative.get('gait_speed_m_per_s'):
            gait_speed_m_per_s = metrics.gait_speed_mm_per_s / 1000.0
            z_scores['gait_speed'] = (gait_speed_m_per_s - normative['gait_speed_m_per_s']) / 0.2
        
        return z_scores
    
    def _estimate_uncertainty(self, metrics: GaitMetrics) -> Dict:
        """Estimate uncertainty bounds for key metrics"""
        # Based on confidence and data quality
        base_uncertainty = (1.0 - metrics.overall_confidence) * 0.1
        
        return {
            'gait_speed_uncertainty_percent': base_uncertainty * 100,
            'joint_angle_uncertainty_deg': base_uncertainty * 5.0,  # ±5° example
            'spatial_uncertainty_mm': base_uncertainty * 10.0
        }
    
    def _generate_clinical_interpretation(self, metrics: GaitMetrics) -> Dict:
        """Generate clinical interpretation of metrics"""
        interpretations = []
        
        # Gait speed interpretation
        gait_speed_m_per_s = metrics.gait_speed_mm_per_s / 1000.0
        if gait_speed_m_per_s < 0.6:
            interpretations.append({
                'metric': 'gait_speed',
                'severity': 'high',
                'interpretation': 'Significantly reduced gait speed (<0.6 m/s) associated with increased fall risk'
            })
        elif gait_speed_m_per_s < 1.0:
            interpretations.append({
                'metric': 'gait_speed',
                'severity': 'moderate',
                'interpretation': 'Reduced gait speed may indicate mobility limitations'
            })
        
        # Stride variability
        if metrics.stride_variability_cv > 5.0:
            interpretations.append({
                'metric': 'stride_variability',
                'severity': 'high',
                'interpretation': 'Elevated stride variability indicates motor control deterioration and increased fall risk'
            })
        
        # Step asymmetry
        if metrics.step_asymmetry_percent > 10.0:
            interpretations.append({
                'metric': 'step_asymmetry',
                'severity': 'moderate',
                'interpretation': 'Step asymmetry may indicate unilateral weakness or pain'
            })
        
        # Clearance
        if metrics.toe_clearance_mm < 50.0:
            interpretations.append({
                'metric': 'toe_clearance',
                'severity': 'high',
                'interpretation': 'Low toe clearance increases trip risk in cluttered environments'
            })
        
        return {
            'interpretations': interpretations,
            'summary': self._generate_summary(interpretations)
        }
    
    def _generate_summary(self, interpretations: List[Dict]) -> str:
        """Generate summary text"""
        if not interpretations:
            return "Gait parameters within normal ranges for age-matched population."
        
        high_severity = [i for i in interpretations if i['severity'] == 'high']
        if high_severity:
            return f"Multiple high-priority concerns identified: {len(high_severity)} metrics require clinical attention."
        
        return f"Moderate concerns identified: {len(interpretations)} metrics may benefit from monitoring."
    
    def export_fhir(self, metrics: GaitMetrics, patient_id: str) -> Dict:
        """Export metrics as FHIR Observation resources"""
        observations = []
        
        # Gait speed observation
        gait_speed_obs = Observation.construct(
            status="final",
            code={
                "coding": [{
                    "system": "http://loinc.org",
                    "code": "33747-0",
                    "display": "Gait speed"
                }]
            },
            valueQuantity={
                "value": metrics.gait_speed_mm_per_s / 1000.0,
                "unit": "m/s",
                "system": "http://unitsofmeasure.org",
                "code": "m/s"
            },
            subject={"reference": f"Patient/{patient_id}"}
        )
        observations.append(gait_speed_obs.dict())
        
        return {
            'fhir_format': 'json',
            'observations': observations
        }


class CaregiverReportGenerator:
    """
    Monitoring dashboard for family caregivers
    Simple, actionable insights with trend tracking
    """
    
    def generate_report(
        self,
        metrics: GaitMetrics,
        previous_metrics: Optional[GaitMetrics] = None,
        analysis_date: Optional[datetime] = None
    ) -> Dict:
        """Generate caregiver-friendly report"""
        
        analysis_date = analysis_date or datetime.now()
        
        # Calculate fall risk indicator
        fall_risk = self._calculate_fall_risk(metrics)
        
        # Calculate trends if previous data available
        trends = {}
        if previous_metrics:
            trends = self._calculate_trends(metrics, previous_metrics)
        
        report = {
            'report_type': 'caregiver',
            'generated_at': analysis_date.isoformat(),
            
            # Fall Risk Indicator
            'fall_risk': {
                'level': fall_risk['level'],
                'color': fall_risk['color'],
                'description': fall_risk['description']
            },
            
            # Key Metrics
            'key_metrics': {
                'walking_speed': {
                    'value': metrics.gait_speed_mm_per_s / 1000.0,
                    'unit': 'm/s',
                    'label': 'Walking Speed'
                },
                'mobility_score': self._calculate_mobility_score(metrics)
            },
            
            # Trends
            'trends': trends,
            
            # Recommendations
            'recommendations': self._generate_recommendations(metrics, fall_risk)
        }
        
        return report
    
    def _calculate_fall_risk(self, metrics: GaitMetrics) -> Dict:
        """Calculate fall risk level (Low/Moderate/High)"""
        risk_score = 0
        
        # Gait speed < 0.6 m/s is high risk
        gait_speed_m_per_s = metrics.gait_speed_mm_per_s / 1000.0
        if gait_speed_m_per_s < 0.6:
            risk_score += 3
        elif gait_speed_m_per_s < 1.0:
            risk_score += 1
        
        # High stride variability
        if metrics.stride_variability_cv > 5.0:
            risk_score += 2
        
        # Low clearance
        if metrics.toe_clearance_mm < 50.0:
            risk_score += 2
        
        # Step asymmetry
        if metrics.step_asymmetry_percent > 10.0:
            risk_score += 1
        
        # Determine level
        if risk_score >= 5:
            return {
                'level': 'high',
                'color': 'red',
                'description': 'High fall risk - recommend immediate clinical consultation'
            }
        elif risk_score >= 3:
            return {
                'level': 'moderate',
                'color': 'yellow',
                'description': 'Moderate fall risk - monitor closely and consider clinical review'
            }
        else:
            return {
                'level': 'low',
                'color': 'green',
                'description': 'Low fall risk - continue regular monitoring'
            }
    
    def _calculate_trends(
        self,
        current: GaitMetrics,
        previous: GaitMetrics
    ) -> Dict:
        """Calculate trends from previous assessment"""
        trends = {}
        
        # Gait speed trend
        speed_change = ((current.gait_speed_mm_per_s - previous.gait_speed_mm_per_s) 
                       / previous.gait_speed_mm_per_s * 100)
        trends['walking_speed'] = {
            'change_percent': speed_change,
            'direction': 'improving' if speed_change > 0 else 'declining',
            'message': f"Walking speed has {'increased' if speed_change > 0 else 'declined'} {abs(speed_change):.1f}% since last assessment"
        }
        
        return trends
    
    def _calculate_mobility_score(self, metrics: GaitMetrics) -> int:
        """Calculate simple mobility score (0-100)"""
        score = 100
        
        # Penalize for various factors
        gait_speed_m_per_s = metrics.gait_speed_mm_per_s / 1000.0
        if gait_speed_m_per_s < 0.6:
            score -= 30
        elif gait_speed_m_per_s < 1.0:
            score -= 15
        
        if metrics.stride_variability_cv > 5.0:
            score -= 20
        
        if metrics.toe_clearance_mm < 50.0:
            score -= 15
        
        return max(0, min(100, int(score)))
    
    def _generate_recommendations(
        self,
        metrics: GaitMetrics,
        fall_risk: Dict
    ) -> List[str]:
        """Generate actionable recommendations"""
        recommendations = []
        
        if fall_risk['level'] == 'high':
            recommendations.append("Schedule immediate consultation with healthcare provider")
            recommendations.append("Consider home safety assessment")
        
        if metrics.gait_speed_mm_per_s / 1000.0 < 1.0:
            recommendations.append("Consider physical therapy or exercise program")
        
        if metrics.toe_clearance_mm < 50.0:
            recommendations.append("Remove trip hazards from walking paths")
            recommendations.append("Ensure adequate lighting in all areas")
        
        if not recommendations:
            recommendations.append("Continue current activity level and regular monitoring")
        
        return recommendations


class OlderAdultReportGenerator:
    """
    Intuitive summary for older adults
    Simple visual feedback with trust-building elements
    """
    
    def generate_report(
        self,
        metrics: GaitMetrics,
        video_overlay_available: bool = False,
        analysis_date: Optional[datetime] = None
    ) -> Dict:
        """Generate older adult-friendly report"""
        
        analysis_date = analysis_date or datetime.now()
        
        # Calculate gait health score
        health_score = self._calculate_gait_health_score(metrics)
        
        report = {
            'report_type': 'older_adult',
            'generated_at': analysis_date.isoformat(),
            
            # Gait Health Score
            'gait_health_score': {
                'score': health_score,
                'out_of': 100,
                'interpretation': self._interpret_health_score(health_score)
            },
            
            # Simple Metrics
            'simple_metrics': {
                'walking_speed': f"{metrics.gait_speed_mm_per_s / 1000.0:.2f} m/s",
                'steps_per_minute': f"{metrics.cadence_steps_per_min:.0f}"
            },
            
            # Visual Feedback
            'visual_feedback': {
                'video_overlay_available': video_overlay_available,
                'skeletal_overlay': 'stick_figure',  # Trust-building: shows focus on movement, not privacy
                'confidence_indicator': 'high' if metrics.overall_confidence > 0.8 else 'medium'
            },
            
            # Encouraging Message
            'message': self._generate_encouraging_message(metrics, health_score)
        }
        
        return report
    
    def _calculate_gait_health_score(self, metrics: GaitMetrics) -> int:
        """Calculate simple 1-100 gait health score"""
        score = 100
        
        # Penalize for risk factors
        gait_speed_m_per_s = metrics.gait_speed_mm_per_s / 1000.0
        if gait_speed_m_per_s < 0.6:
            score -= 25
        elif gait_speed_m_per_s < 1.0:
            score -= 10
        
        if metrics.stride_variability_cv > 5.0:
            score -= 15
        
        if metrics.step_asymmetry_percent > 10.0:
            score -= 10
        
        if metrics.toe_clearance_mm < 50.0:
            score -= 10
        
        return max(1, min(100, int(score)))
    
    def _interpret_health_score(self, score: int) -> str:
        """Interpret health score in simple terms"""
        if score >= 80:
            return "Excellent - Your walking looks strong!"
        elif score >= 60:
            return "Good - Keep up your regular activity"
        elif score >= 40:
            return "Fair - Consider talking to your doctor about mobility"
        else:
            return "Needs attention - Please consult with your healthcare provider"
    
    def _generate_encouraging_message(
        self,
        metrics: GaitMetrics,
        health_score: int
    ) -> str:
        """Generate encouraging, non-alarming message"""
        if health_score >= 80:
            return "Your movement analysis shows you're maintaining good mobility. Keep up the great work!"
        elif health_score >= 60:
            return "Your walking patterns are generally good. Regular activity helps maintain mobility."
        else:
            return "This analysis helps track your mobility over time. Share these results with your healthcare team."


class ReportingService:
    """
    Main reporting service
    Coordinates report generation for all audiences
    """
    
    def __init__(self):
        self.medical_generator = MedicalReportGenerator()
        self.caregiver_generator = CaregiverReportGenerator()
        self.older_adult_generator = OlderAdultReportGenerator()
        logger.info("Reporting service initialized")
    
    def generate_all_reports(
        self,
        metrics: GaitMetrics,
        patient_id: Optional[str] = None,
        previous_metrics: Optional[GaitMetrics] = None,
        video_overlay_available: bool = False
    ) -> Dict:
        """Generate reports for all audiences"""
        analysis_date = datetime.now()
        
        return {
            'medical': self.medical_generator.generate_report(
                metrics, patient_id=patient_id, analysis_date=analysis_date
            ),
            'caregiver': self.caregiver_generator.generate_report(
                metrics, previous_metrics=previous_metrics, analysis_date=analysis_date
            ),
            'older_adult': self.older_adult_generator.generate_report(
                metrics, video_overlay_available=video_overlay_available, analysis_date=analysis_date
            ),
            'generated_at': analysis_date.isoformat()
        }



