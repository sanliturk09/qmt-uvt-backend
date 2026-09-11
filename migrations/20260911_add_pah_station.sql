/* UVT_DB only: create the PAH station and repair previously imported PAH jobs. */
IF NOT EXISTS (SELECT 1 FROM dbo.StationCategories WHERE code = 'PAH')
BEGIN
    INSERT INTO dbo.StationCategories (code, category_name)
    VALUES ('PAH', N'Spiral Mk. PAH KIRMA');
END;

DECLARE @PahCategoryId INT = (SELECT id FROM dbo.StationCategories WHERE code = 'PAH');

IF NOT EXISTS (SELECT 1 FROM dbo.Workstations WHERE station_code = 'PAH-01')
BEGIN
    INSERT INTO dbo.Workstations (category_id, station_code, station_name, is_active)
    VALUES (@PahCategoryId, 'PAH-01', N'PAH Kırma', 1);
END;

DECLARE @PahWorkstationId INT = (SELECT id FROM dbo.Workstations WHERE station_code = 'PAH-01');

/* Existing imports had no category because PAH did not exist during sync. */
UPDATE op
SET
    category_id = @PahCategoryId,
    category_name = N'Spiral Mk. PAH KIRMA',
    status = CASE WHEN op.is_unlocked = 1 AND op.status = 'LOCKED' THEN 'PENDING' ELSE op.status END
FROM dbo.ProductionOperations op
WHERE op.category_id IS NULL
  AND op.category_name LIKE N'%PAH%';

/*
   If the preceding operation completed before PAH existed, it could not pick
   a PAH workstation.  Repair those already-open jobs immediately; future
   transitions use the normal complete_job routing and get this assignment
   automatically on the same day.
*/
UPDATE op
SET
    scheduled_date = ISNULL(op.scheduled_date, CAST(GETDATE() AS DATE)),
    assigned_workstation_id = ISNULL(op.assigned_workstation_id, @PahWorkstationId)
FROM dbo.ProductionOperations op
WHERE op.category_id = @PahCategoryId
  AND op.is_unlocked = 1
  AND op.status IN ('PENDING', 'PAUSED', 'IN_PROGRESS');
