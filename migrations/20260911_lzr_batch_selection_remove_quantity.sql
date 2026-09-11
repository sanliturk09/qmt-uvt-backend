/* Run once in UVT_DB only if the original LZR migration was already executed. */
IF OBJECT_ID(N'dbo.CK_LzrBatchSelections_quantity_positive', N'C') IS NOT NULL
    ALTER TABLE dbo.LzrBatchSelections DROP CONSTRAINT CK_LzrBatchSelections_quantity_positive;

IF COL_LENGTH(N'dbo.LzrBatchSelections', N'selected_quantity') IS NOT NULL
    ALTER TABLE dbo.LzrBatchSelections ALTER COLUMN selected_quantity DECIMAL(18, 6) NULL;
