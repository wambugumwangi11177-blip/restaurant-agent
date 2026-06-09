"""
backend/ai/orchestrator/proactive_executive.py
───────────────────────────────────────────────
Proactive Executive Agent - Extension of the Executive Agent
Adds goal initiation, planning, and multi-agent collaboration capabilities
while maintaining backward compatibility with existing reactive handlers.

This agent:
1. Maintains all existing reactive event handlers (backward compatible)
2. Adds proactive goal-setting and planning capabilities
3. Uses the new agent communication framework for collaboration
4. Implements simple reasoning loops (Observe-Orient-Decide-Act)
5. Tracks goals and learns from outcomes
"""

import logging
import json
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session
from enum import Enum

from database import SessionLocal
import models
from events.bus import subscribe, EventType, emit_async
from ai.memory import store as memory
from ai.evaluation.tracker import write_audit_log
from ai.communication import (
    get_communication_hub,
    MessageType,
    Priority,
    AgentCapability
)
from ai.profit.intelligence import get_profit_intelligence

logger = logging.getLogger("ai.proactive_executive")


class GoalStatus(str, Enum):
    """Status of a goal"""
    PROPOSED = "proposed"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class GoalType(str, Enum):
    """Types of goals the executive agent can pursue"""
    OPTIMIZE_PROFITABILITY = "optimize.profitability"
    IMPROVE_CUSTOMER_SATISFACTION = "improve.customer_satisfaction"
    REDUCE_WASTE = "reduce.waste"
    INCREASE_TABLE_TURNOVER = "increase.table_turnover"
    OPTIMIZE_STAFFING = "optimize.staffing"
    MANAGE_INVENTORY = "manage.inventory"
    LAUNCH_MARKETING_CAMPAIGN = "launch.marketing_campaign"


class ProactiveExecutive:
    """
    Proactive Executive Agent that can initiate goals and collaborate with other agents
    """

    def __init__(self, tenant_id: str = "default"):
        self.tenant_id = tenant_id
        self.communication_hub = None
        self.active_goals: Dict[str, Dict] = {}
        self.goal_history: List[Dict] = []
        self.reasoning_cycles: Dict[str, List] = {}  # Track reasoning for each goal
        self.pending_responses: Dict[str, Dict] = {}  # Store responses by correlation_id
        self.pending_queries: Dict[str, Dict] = {}    # Store pending queries by correlation_id
        self.config = {
            "reasoning_cycle_limit": 5,  # Max OODA loops per goal
            "goal_timeout_hours": 24,
            "collaboration_timeout_minutes": 10
        }

    def initialize(self, db: Session):
        """Initialize the proactive executive with database connection"""
        self.communication_hub = get_communication_hub(db, self.tenant_id)

        # Register this agent in the system
        agent_id = self.communication_hub.register_agent(
            agent_id="proactive_executive_v1",
            agent_name="Proactive Executive Agent",
            capabilities=[
                AgentCapability.GOAL_PLANNING,
                AgentCapability.REASONING,
                AgentCapability.LEARNING
            ],
            version="1.0.0",
            description="Executive agent that sets goals, plans, and coordinates other agents",
            config={
                "reasoning_cycle_limit": 5,  # Max OODA loops per goal
                "goal_timeout_hours": 24,
                "collaboration_timeout_minutes": 10
            }
        )
        logger.info(f"[ProactiveExecutive] Initialized with agent ID: {agent_id}")

        # Subscribe to relevant events for reactive behavior (maintains backward compatibility)
        self._register_reactive_handlers()

        # Subscribe to response messages for agent communication
        self.communication_hub.subscribe_local(MessageType.RESPONSE, self._handle_response)

        # Start background goal processing
        self._start_goal_processor()

    def _get_tenant_id_for_query(self, db: Session) -> Optional[int]:
        """Resolve tenant identifier to actual database tenant ID for queries."""
        try:
            # If already an integer, use it directly
            if isinstance(self.tenant_id, int):
                return self.tenant_id

            # If string, try to look up tenant by name
            if isinstance(self.tenant_id, str):
                tenant = db.query(models.Tenant).filter(models.Tenant.name == self.tenant_id).first()
                if tenant:
                    return tenant.id

                # If not found by name, try to see if it's a string representation of an integer
                try:
                    tenant_id_int = int(self.tenant_id)
                    tenant = db.query(models.Tenant).filter(models.Tenant.id == tenant_id_int).first()
                    if tenant:
                        return tenant.id
                except ValueError:
                    pass

            # Fallback: use first tenant in system
            first_tenant = db.query(models.Tenant).first()
            if first_tenant:
                return first_tenant.id

            return None
        except Exception as e:
            logger.error(f"[ProactiveExecutive] Failed to resolve tenant ID: {e}")
            return None

    def _register_reactive_handlers(self):
        """Register existing reactive handlers for backward compatibility"""
        # These maintain the existing behavior from the original executive agent
        subscribe(EventType.STOCK_CRITICAL, self._handle_stock_critical_reactive)
        subscribe(EventType.STOCK_DEPLETED, self._handle_stock_depleted_reactive)
        subscribe(EventType.RECOMMENDATION_APPROVED, self._handle_recommendation_approved_reactive)
        subscribe(EventType.ORDER_PAID, self._handle_order_paid_mpesa_reactive)
        subscribe(EventType.RESERVATION_NO_SHOW, self._handle_reservation_no_show_reactive)
        subscribe(EventType.PURCHASE_ORDER_LATE, self._handle_purchase_order_late_reactive)
        subscribe(EventType.AGENT_FAILED, self._handle_agent_failed_reactive)

        logger.info("[ProactiveExecutive] Registered reactive handlers (backward compatibility)")

    # ────────────────────────────────────────────────────────────────
    # REACTIVE HANDLERS (Maintain existing behavior)
    # ────────────────────────────────────────────────────────────────

    def _handle_stock_critical_reactive(self, payload: dict):
        """Wrapper to maintain existing reactive behavior"""
        from ai.orchestrator.executive import on_stock_critical
        on_stock_critical(payload)

    def _handle_stock_depleted_reactive(self, payload: dict):
        """Wrapper to maintain existing reactive behavior"""
        from ai.orchestrator.executive import on_stock_depleted
        on_stock_depleted(payload)

    def _handle_recommendation_approved_reactive(self, payload: dict):
        """Wrapper to maintain existing reactive behavior"""
        from ai.orchestrator.executive import on_recommendation_approved
        on_recommendation_approved(payload)

    def _handle_order_paid_mpesa_reactive(self, payload: dict):
        """Wrapper to maintain existing reactive behavior"""
        from ai.orchestrator.executive import on_order_paid_mpesa
        on_order_paid_mpesa(payload)

    def _handle_reservation_no_show_reactive(self, payload: dict):
        """Wrapper to maintain existing reactive behavior"""
        from ai.orchestrator.executive import on_reservation_no_show
        on_reservation_no_show(payload)

    def _handle_purchase_order_late_reactive(self, payload: dict):
        """Wrapper to maintain existing reactive behavior"""
        from ai.orchestrator.executive import on_purchase_order_late
        on_purchase_order_late(payload)

    def _handle_agent_failed_reactive(self, payload: dict):
        """Wrapper to maintain existing reactive behavior"""
        from ai.orchestrator.executive import on_agent_failed
        on_agent_failed(payload)

    # ────────────────────────────────────────────────────────────────
    # PROACTIVE CAPABILITIES
    # ────────────────────────────────────────────────────────────────

    def propose_goal(self, goal_type: GoalType, description: str,
                    success_criteria: Dict[str, Any], priority: int = 1,
                    suggested_by: str = "system") -> str:
        """
        Propose a new goal for the executive agent to pursue
        Returns the goal ID
        """
        goal_id = str(uuid.uuid4())

        goal = {
            'id': goal_id,
            'type': goal_type.value,
            'description': description,
            'success_criteria': success_criteria,
            'priority': priority,
            'status': GoalStatus.PROPOSED,
            'proposed_at': datetime.utcnow(),
            'proposed_by': suggested_by,
            'updated_at': datetime.utcnow(),
            'reasoning_history': [],
            'actions_taken': [],
            'metrics': {}
        }

        self.active_goals[goal_id] = goal
        self.goal_history.append(goal.copy())

        # Communicate the goal proposal to other agents
        if self.communication_hub:
            self.communication_hub.send_message(
                sender_agent="proactive_executive_v1",
                message_type=MessageType.GOAL,
                body={
                    'goal_id': goal_id,
                    'goal_type': goal_type.value,
                    'description': description,
                    'success_criteria': success_criteria,
                    'priority': priority
                },
                priority=Priority.HIGH if priority <= 2 else Priority.MEDIUM,
                correlation_id=goal_id
            )

        logger.info(f"[ProactiveExecutive] Proposed goal {goal_id}: {description}")
        return goal_id

    def activate_goal(self, goal_id: str) -> bool:
        """Activate a proposed goal"""
        if goal_id not in self.active_goals:
            logger.warning(f"[ProactiveExecutive] Goal {goal_id} not found")
            return False

        goal = self.active_goals[goal_id]
        if goal['status'] != GoalStatus.PROPOSED:
            logger.warning(f"[ProactiveExecutive] Goal {goal_id} is not in PROPOSED status")
            return False

        goal['status'] = GoalStatus.ACTIVE
        goal['activated_at'] = datetime.utcnow()
        goal['updated_at'] = datetime.utcnow()

        logger.info(f"[ProactiveExecutive] Activated goal {goal_id}: {goal['description']}")

        # Start the reasoning cycle for this goal
        self._start_reasoning_cycle(goal_id)

        return True

    def _start_reasoning_cycle(self, goal_id: str):
        """Start an OODA (Observe-Orient-Decide-Act) loop for a goal"""
        if goal_id not in self.active_goals:
            return

        goal = self.active_goals[goal_id]
        if goal['status'] != GoalStatus.ACTIVE:
            return

        # Initialize reasoning history for this goal if not present
        if goal_id not in self.reasoning_cycles:
            self.reasoning_cycles[goal_id] = []

        cycle_number = len(self.reasoning_cycles[goal_id]) + 1

        logger.info(f"[ProactiveExecutive] Starting reasoning cycle {cycle_number} for goal {goal_id}")

        # OBSERVE: Gather current state from relevant agents
        observation = self._observe_goal_state(goal_id)

        # ORIENT: Analyze the observation against goal criteria
        orientation = self._orient_goal_state(goal_id, observation)

        # DECIDE: Determine what actions to take
        decision = self._decide_goal_actions(goal_id, observation, orientation)

        # ACT: Execute the decided actions
        if decision['actions']:
            self._act_on_goal_decision(goal_id, decision)

        # Record the reasoning cycle
        cycle_record = {
            'cycle_number': cycle_number,
            'timestamp': datetime.utcnow(),
            'observe': observation,
            'orient': orientation,
            'decide': decision,
            'act_duration_ms': 0  # Will be filled after actions complete
        }

        self.reasoning_cycles[goal_id].append(cycle_record)
        goal['reasoning_history'].append(cycle_record)
        goal['updated_at'] = datetime.utcnow()

        # Check if goal is complete
        if self._is_goal_complete(goal_id):
            self._complete_goal(goal_id)
        elif cycle_number >= self.config.get("reasoning_cycle_limit", 5):
            # Max cycles reached
            logger.info(f"[ProactiveExecutive] Max reasoning cycles reached for goal {goal_id}")
            self._complete_goal(goal_id, success=False)
        else:
            # Schedule next cycle (in reality, this would be event-driven or timed)
            # For now, we'll rely on events triggering new observations
            pass

    def _handle_response(self, message: Dict):
        """Handle incoming response messages"""
        try:
            correlation_id = message.get('correlation_id')
            if correlation_id:
                self.pending_responses[correlation_id] = message
                logger.debug(f"[ProactiveExecutive] Stored response for correlation_id: {correlation_id}")
        except Exception as e:
            logger.error(f"[ProactiveExecutive] Failed to handle response: {e}")

    def _observe_goal_state(self, goal_id: str) -> Dict[str, Any]:
        """Gather current state relevant to the goal from various agents"""
        if not self.communication_hub:
            return {}

        goal = self.active_goals[goal_id]
        observation = {
            'goal_id': goal_id,
            'timestamp': datetime.utcnow(),
            'data_sources': {}
        }

        # Based on goal type, query relevant agents
        if goal['type'] == GoalType.OPTIMIZE_PROFITABILITY.value:
            # Query profit intelligence directly (since it's a local function)
            db = SessionLocal()
            try:
                # Resolve the tenant ID to actual database ID
                tenant_id_resolved = self._get_tenant_id_for_query(db)
                if tenant_id_resolved is None:
                    observation['data_sources']['profit'] = {'error': 'tenant_not_found'}
                else:
                    restaurant = db.query(models.Restaurant).filter(models.Restaurant.id == tenant_id_resolved).first()
                    if restaurant:
                        profit_data = get_profit_intelligence(db, restaurant.id)
                        observation['data_sources']['profit'] = profit_data
                    else:
                        observation['data_sources']['profit'] = {'error': 'restaurant_not_found'}
            finally:
                db.close()
            # Also query pricing and inventory agents via communication hub (for demonstration)
            # We'll leave these as is for now, but note that we don't wait for responses
            observation['data_sources']['pricing'] = self._query_agent_capability(
                'pricing_intelligence_v1',
                AgentCapability.PRICING_ANALYSIS,
                {'analysis_type': 'margin_leaks'}
            )
            observation['data_sources']['inventory'] = self._query_agent_capability(
                'inventory_predictor_v1',
                AgentCapability.INVENTORY_PREDICTION,
                {'analysis_type': 'waste_analysis'}
            )

        elif goal['type'] == GoalType.REDUCE_WASTE.value:
            observation['data_sources']['inventory'] = self._query_agent_capability(
                'inventory_predictor_v1',
                AgentCapability.INVENTORY_PREDICTION,
                {'analysis_type': 'spoilage_risk'}
            )
            observation['data_sources']['menu'] = self._query_agent_capability(
                'menu_engineer_v1',
                AgentCapability.MENU_ENGINEERING,
                {'analysis_type': 'item_performance'}
            )

        # Add more goal types as needed...

        # Include any pending responses for this goal
        goal_responses = []
        for corr_id, response in list(self.pending_responses.items()):
            # Check if this response is for this goal (by checking if the correlation_id is related to the goal)
            # For simplicity, we'll assume that any response with a correlation_id that contains the goal_id is for this goal
            if goal_id in corr_id:
                goal_responses.append(response)
                # Remove the response from pending to avoid duplicate processing
                del self.pending_responses[corr_id]
        if goal_responses:
            observation['data_sources']['responses'] = goal_responses

        return observation

    def _orient_goal_state(self, goal_id: str, observation: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze observation against goal criteria to determine current state"""
        goal = self.active_goals[goal_id]
        orientation = {
            'goal_id': goal_id,
            'timestamp': datetime.utcnow(),
            'goal_alignment': 0.0,  # 0-1 scale
            'gaps': [],
            'strengths': [],
            'confidence': 0.0
        }

        # Simple alignment calculation (would be more sophisticated in practice)
        if goal['type'] == GoalType.OPTIMIZE_PROFITABILITY.value:
            profit_data = observation.get('data_sources', {}).get('profit', {})
            if profit_data and 'error' not in profit_data:
                current_margin = profit_data.get('gross_margin_pct', 0)
                target_margin = goal['success_criteria'].get('target_margin_pct', 70)

                if target_margin > 0:
                    alignment = min(current_margin / target_margin, 1.0)
                    orientation['goal_alignment'] = alignment

                    if alignment >= 0.9:
                        orientation['strengths'].append(f"Margin at {current_margin:.1f}% (target: {target_margin}%)")
                    else:
                        orientation['gaps'].append(f"Margin at {current_margin:.1f}% below target {target_margin}%")

                    orientation['confidence'] = 0.8  # Based on data quality
            else:
                orientation['gaps'].append("Failed to retrieve profit data")
                orientation['confidence'] = 0.0

        # Add more goal-type specific orientation logic...

        return orientation

    def _decide_goal_actions(self, goal_id: str, observation: Dict, orientation: Dict) -> Dict[str, Any]:
        """Decide what actions to take based on observation and orientation"""
        decision = {
            'goal_id': goal_id,
            'timestamp': datetime.utcnow(),
            'actions': [],  # List of actions to take
            'reasoning': '',
            'confidence': 0.0
        }

        goal = self.active_goals[goal_id]

        # Simple decision logic (would be more sophisticated with ML/rule engine)
        if goal['type'] == GoalType.OPTIMIZE_PROFITABILITY.value:
            gaps = orientation.get('gaps', [])
            if gaps:
                # If we have margin gaps, decide to communicate with pricing agent
                if any('margin' in gap.lower() for gap in gaps):
                    decision['actions'].append({
                        'type': 'communicate',
                        'target_agent': 'pricing_intelligence_v1',
                        'message_type': MessageType.QUERY,
                        'content': {
                            'request': 'analyze_margin_leaks',
                            'context': 'profitability_optimization_goal',
                            'goal_id': goal_id
                        },
                        'expected_response': 'detailed_margin_analysis_with_recommendations'
                    })
                    decision['reasoning'] = "Identified margin gaps, requesting pricing analysis for optimization recommendations"
                    decision['confidence'] = 0.7
                elif any('inventory' in gap.lower() or 'waste' in gap.lower() for gap in gaps):
                    decision['actions'].append({
                        'type': 'communicate',
                        'target_agent': 'inventory_predictor_v1',
                        'message_type': MessageType.QUERY,
                        'content': {
                            'request': 'analyze_waste_sources',
                            'context': 'profitability_optimization_goal',
                            'goal_id': goal_id
                        },
                        'expected_response': 'waste_analysis_with_reduction_recommendations'
                    })
                    decision['reasoning'] = "Identified inventory/waste issues, requesting analysis for reduction strategies"
                    decision['confidence'] = 0.75

        # If no specific actions determined but we're not aligned, request general analysis
        if not decision['actions'] and orientation.get('goal_alignment', 1.0) < 0.8:
            # Request comprehensive analysis from relevant agents based on goal type
            if goal['type'] == GoalType.OPTIMIZE_PROFITABILITY.value:
                decision['actions'].append({
                    'type': 'communicate',
                    'target_agent': 'profit_intelligence_v1',
                    'message_type': MessageType.QUERY,
                    'content': {
                        'request': 'comprehensive_profit_analysis',
                        'context': 'goal_driven_analysis',
                        'goal_id': goal_id
                    }
                })
                decision['reasoning'] = "Goal not sufficiently aligned, requesting comprehensive profit analysis"
                decision['confidence'] = 0.6

        return decision

    def _act_on_goal_decision(self, goal_id: str, decision: Dict[str, Any]):
        """Execute the decided actions"""
        start_time = datetime.utcnow()

        for action in decision.get('actions', []):
            action_id = str(uuid.uuid4())
            action_record = {
                'action_id': action_id,
                'timestamp': datetime.utcnow(),
                'type': action['type'],
                'details': action,
                'status': 'initiated'
            }

            goal = self.active_goals[goal_id]
            goal['actions_taken'].append(action_record)

            if action['type'] == 'communicate':
                # Send message to target agent
                if self.communication_hub:
                    try:
                        self.communication_hub.send_message(
                            sender_agent="proactive_executive_v1",
                            recipient_agent=action['target_agent'],
                            message_type=action['message_type'],
                            body=action['content'],
                            correlation_id=f"{goal_id}_{action_id}",
                            priority=Priority.MEDIUM
                        )
                        action_record['status'] = 'sent'
                        logger.info(f"[ProactiveExecutive] Sent {action['message_type'].value} to {action['target_agent']} for goal {goal_id}")
                    except Exception as e:
                        action_record['status'] = 'failed'
                        action_record['error'] = str(e)
                        logger.error(f"[ProactiveExecutive] Failed to send message: {e}")

            # Add other action types as needed (execute_script, update_config, etc.)

        # Update act duration in the last reasoning cycle
        if self.reasoning_cycles[goal_id]:
            last_cycle = self.reasoning_cycles[goal_id][-1]
            last_cycle['act_duration_ms'] = int((datetime.utcnow() - start_time).total_seconds() * 1000)

    def _is_goal_complete(self, goal_id: str) -> bool:
        """Check if a goal has been achieved based on success criteria"""
        if goal_id not in self.active_goals:
            return False

        goal = self.active_goals[goal_id]
        # Simple completion check - in reality this would evaluate metrics against success_criteria
        # For now, we'll consider it complete after a few cycles if we've taken actions
        actions_taken = len(goal.get('actions_taken', []))
        cycles_completed = len(self.reasoning_cycles[goal_id])

        # Goal is complete if we've taken meaningful actions and gone through reasoning cycles
        return actions_taken > 0 and cycles_completed >= 2

    def _complete_goal(self, goal_id: str, success: bool = True):
        """Mark a goal as complete"""
        if goal_id not in self.active_goals:
            return

        goal = self.active_goals[goal_id]
        goal['status'] = GoalStatus.COMPLETED if success else GoalStatus.FAILED
        goal['completed_at'] = datetime.utcnow()
        goal['updated_at'] = datetime.utcnow()
        goal['success'] = success

        logger.info(f"[ProactiveExecutive] Goal {goal_id} {'completed' if success else 'failed'}: {goal['description']}")

        # Notify other agents of goal completion
        if self.communication_hub:
            self.communication_hub.send_message(
                sender_agent="proactive_executive_v1",
                message_type=MessageType.RESULT,
                body={
                    'goal_id': goal_id,
                    'goal_type': goal['type'],
                    'description': goal['description'],
                    'success': success,
                    'actions_taken': len(goal.get('actions_taken', [])),
                    'reasoning_cycles': len(self.reasoning_cycles.get(goal_id, [])),
                    'completion_time': goal['completed_at'].isoformat() if goal.get('completed_at') else None
                },
                priority=Priority.HIGH,
                correlation_id=goal_id
            )

    def _query_agent_capability(self, agent_id: str, capability: AgentCapability,
                               query_params: Dict[str, Any]) -> Dict[str, Any]:
        """Query another agent for specific information"""
        if not self.communication_hub:
            return {'error': 'communication_hub_not_available'}

        # Find agent with this capability
        agents = self.communication_hub.find_agents_by_capability(capability)
        target_agent = None

        for agent in agents:
            if agent['id'] == agent_id:
                target_agent = agent
                break

        if not target_agent and agents:
            # Use first available agent with capability
            target_agent = agents[0]
            logger.info(f"[ProactiveExecutive] Using {target_agent['id']} instead of requested {agent_id} for {capability}")

        if not target_agent:
            logger.warning(f"[ProactiveExecutive] No agent found with capability {capability.value}")
            return {'error': 'no_agent_available'}

        # Send query message and wait for response (simplified - real implementation would use callbacks/futures)
        correlation_id = str(uuid.uuid4())
        try:
            self.communication_hub.send_message(
                sender_agent="proactive_executive_v1",
                recipient_agent=target_agent['id'],
                message_type=MessageType.QUERY,
                body={
                    'request': query_params.get('request', 'general_query'),
                    'parameters': query_params,
                    'context': 'goal_driven_observation'
                },
                correlation_id=correlation_id,
                priority=Priority.MEDIUM,
                ttl_minutes=5  # Short timeout for queries
            )

            # Store the pending query so we can match the response later
            self.pending_queries[correlation_id] = {
                'timestamp': datetime.utcnow(),
                'goal_id': None,  # We don't have the goal_id here, but we can store it if needed
                'agent_id': agent_id,
                'capability': capability.value
            }

            # In a real implementation, we'd wait for the response via callback or polling
            # For now, we'll return a placeholder indicating the query was sent
            return {
                'query_sent': True,
                'target_agent': target_agent['id'],
                'capability': capability.value,
                'correlation_id': correlation_id,
                'note': 'Response will be processed asynchronously via message handlers'
            }

        except Exception as e:
            logger.error(f"[ProactiveExecutive] Failed to query agent {target_agent['id'] if target_agent else 'unknown'}: {e}")
            return {'error': str(e)}

    def _start_goal_processor(self):
        """Start background processing for goals (simplified)"""
        # In a real implementation, this would be a proper background task
        # For now, we'll rely on events triggering observations
        logger.info("[ProactiveExecutive] Goal processor started (event-driven)")

    # ────────────────────────────────────────────────────────────────
    # PUBLIC INTERFACE
    # ────────────────────────────────────────────────────────────────

    def get_active_goals(self) -> List[Dict]:
        """Get all active goals"""
        return [
            {k: v for k, v in goal.items() if k not in ['reasoning_history', 'actions_taken']}
            for goal in self.active_goals.values()
            if goal['status'] in [GoalStatus.PROPOSED, GoalStatus.ACTIVE, GoalStatus.PAUSED]
        ]

    def get_goal_details(self, goal_id: str) -> Optional[Dict]:
        """Get detailed information about a specific goal"""
        if goal_id not in self.active_goals:
            return None

        goal = self.active_goals[goal_id].copy()
        # Include reasoning and action history
        goal['reasoning_history'] = self.reasoning_cycles.get(goal_id, [])
        return goal

    def shutdown(self):
        """Shutdown the proactive executive gracefully"""
        logger.info("[ProactiveExecutive] Shutting down")
        # In a real implementation, we'd clean up background tasks here


# Global instance
_proactive_executive: Optional[ProactiveExecutive] = None


def get_proactive_executive(tenant_id: str = "default") -> ProactiveExecutive:
    """Get or create the global proactive executive instance"""
    global _proactive_executive
    if _proactive_executive is None:
        _proactive_executive = ProactiveExecutive(tenant_id)
    return _proactive_executive


def initialize_proactive_executive(db: Session, tenant_id: str = "default"):
    """Initialize the proactive executive with a database session"""
    executive = get_proactive_executive(tenant_id)
    executive.initialize(db)
    return executive