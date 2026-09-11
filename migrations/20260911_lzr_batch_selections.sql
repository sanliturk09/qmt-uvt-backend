/*
   UVT only: this table records the batch lots chosen by LZR operators.
   It never writes to SAP Business One tables.
*/
IF OBJECT_ID(N'dbo.LzrBatchSelections', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.LzrBatchSelections (
        id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        operation_id INT NOT NULL,
        material_code NVARCHAR(100) NOT NULL,
        batch_number NVARCHAR(100) NOT NULL,
        selected_quantity DECIMAL(18, 6) NULL,
        selected_by_user_id INT NOT NULL,
        selected_at_utc DATETIME2 NOT NULL CONSTRAINT DF_LzrBatchSelections_selected_at_utc DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_LzrBatchSelections_operation FOREIGN KEY (operation_id) REFERENCES dbo.ProductionOperations(id),
        CONSTRAINT FK_LzrBatchSelections_user FOREIGN KEY (selected_by_user_id) REFERENCES dbo.Users(id)
    );
    CREATE INDEX IX_LzrBatchSelections_operation ON dbo.LzrBatchSelections(operation_id);
END;
