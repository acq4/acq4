Analysis Databases
==================

ACQ4 uses SQLite databases to store the results of various analyses. 

Analysis databases are created and managed in the Data Manager's Analysis tab. When a new database is created it has 3 tables: DbParameters, TableConfig and ColumnConfig. The DbParameters table keeps track of various parameters that apply to the whole database. It is initialized with three records of Param:value pairs: a Base Directory whose default value is the top-level directory set in the Data Manager, a DB Version which defaults to the current version of database analysis software, and a description which is blank by default. The TableConfig and ColumnConfig tables are used internally by ACQ4 to define how columns in different tables should be linked together, and how data from the database should be read into memory when it is used during analysis operations.

