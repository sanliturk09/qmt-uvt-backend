/* UVT_DB only. Adds sales-order traceability columns; SAP B1 is never changed. */
IF COL_LENGTH(N'dbo.ProductionOrders', N'sales_order_doc_num') IS NULL
    ALTER TABLE dbo.ProductionOrders ADD sales_order_doc_num INT NULL;

IF COL_LENGTH(N'dbo.ProductionOrders', N'customer_ref_no') IS NULL
    ALTER TABLE dbo.ProductionOrders ADD customer_ref_no NVARCHAR(254) NULL;

IF COL_LENGTH(N'dbo.ProductionOrders', N'sales_delivery_date') IS NULL
    ALTER TABLE dbo.ProductionOrders ADD sales_delivery_date DATE NULL;
