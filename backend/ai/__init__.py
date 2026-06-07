# AI Intelligence Engine
# This package contains the AI services that power the "Restaurant Brain"

# Communication infrastructure for agentic collaboration
from .communication import (
    CommunicationHub,
    MessageType,
    Priority,
    AgentCapability,
    get_communication_hub
)

# Existing AI modules (will be imported as needed)
# from . import profit, pricing, inventory_predictor, revenue_forecaster, etc.