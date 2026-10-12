from database.database import engine
from database.models import Base

print('REPORT_DATABASE_OK')
print('Database:', engine.url.database)
print('Tables:')
for table in Base.metadata.sorted_tables:
    print(' -', table.name)
