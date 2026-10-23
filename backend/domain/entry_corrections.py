"""A reversed count stays in the audit trail but is no longer physical evidence."""
import json
import models


def valid_count_filters(db, rid):
    entries=db.query(models.OperationEntry).filter(models.OperationEntry.restaurant_id==rid,
        models.OperationEntry.kind=='count',models.OperationEntry.undone_at.isnot(None)).all()
    invalid=[json.loads(e.result).get(key) for e in entries for key in ('count_id','reversal_count_id')]
    return [models.StockCount.id.notin_([i for i in invalid if i is not None])]


def valid_movement_filters(db,rid):
    entries=db.query(models.OperationEntry).filter(models.OperationEntry.restaurant_id==rid,
        models.OperationEntry.kind.in_(['count','waste']),models.OperationEntry.undone_at.isnot(None)).all()
    invalid=[json.loads(e.result).get(key) for e in entries for key in ('movement_id','reversal_movement_id')]
    return [models.StockMovement.id.notin_([i for i in invalid if i is not None])]
