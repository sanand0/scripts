---
title: qsv
docs: https://github.com/dathere/qsv
---

```bash
# Infer delimiter/header/preamble/quote char, record counts, MIME-type detector
qsv sniff data.csv

# Infer per-column field, type, basic (sum, min, max, ...) and advanced stats (cv, nullcount, max_precision, sparsity, ...)
qsv stats data.csv

# Print first five rows
qsv slice -l 5 data.csv | qsv table

# Get 10 random rows. Pick columns 1, 3, 4, 5
qsv sample -n 10 data.csv | qsv select 1,3-5

# Select columns ColA, ColC to anything matching ColD, column 6 onwards, not columns 10-11
qsv select ColA,ColC-/ColD/,6-,!10-11

# Sort by ColA, then ColB, in numeric, natural order, descending, ignoring case
qsv sort --select ColA,ColB --numeric --natural --reverse --ignore-case data.csv
# Deduplicate based on ColA, ColB, in numeric, ignoring case
qsv dedup --select ColA,ColB --numeric --ignore-case data.csv

# Regex replace to drop text
qsv apply operations regex_replace --comparand "PATTERN" --replacement "<NULL>" -c cleaned_col "Original Column" data.csv

# Join two CSVs (note: column is repeated)
qsv join "Email" a.csv "Email" b.csv

# Convert file formats
qsv tojsonl data.csv --output data.jsonl
qsv jsonl data.jsonl --output data.csv
qsv to postgres output.sql data.csv
qsv to sqlite output.db data.csv
qsv to xlsx output.xlsx data.csv
qsv to ods output.ods data.csv
qsv to parquet output.parquet data.csv
qsv to datapackage output.json data.csv
```

- Set delimiter via `--delimiter`
- Save to file via `--output`.
- There is no `--limit` parameter.

More commands. Run `qsv $COMMAND --help` for details:

```
apply       Apply series of transformations to a column
behead      Drop header from CSV file
cat         Concatenate by row or column
datefmt     Format date/datetime strings
describegpt Infer extended metadata using a LLM
diff        Find the difference between two CSVs
edit        Replace a cell's value specified by row and column
enum        Add a new column enumerating CSV lines
excel       Exports an Excel sheet to a CSV
exclude     Excludes the records in one CSV from another
explode     Explode rows based on some column separator
extdedup    Remove duplicates rows from an arbitrarily large text file
extsort     Sort arbitrarily large text file
fetch       Fetches data from web services for every row using HTTP Get.
fetchpost   Fetches data from web services for every row using HTTP Post.
fill        Fill empty values
fixlengths  Makes all records have same length
flatten     Show one field per line
fmt         Format CSV output (change field delimiter)
foreach     Loop over a CSV file to execute bash commands
frequency   Show per-column frequency tables
geocode     Geocodes a location against the Geonames cities database.
geoconvert  Convert between spatial formats & CSV, including GeoJSON, SHP & more
input       Read CSVs w/ special quoting, skipping, trimming & transcoding rules
joinp       Join CSV files using the Pola.rs engine
json        Convert JSON to CSV
lens        View a CSV file interactively
luau        Execute Luau script on CSV data
partition   Partition CSV data based on a column value
pivotp      Pivots CSV files using the Pola.rs engine
pseudo      Pseudonymise the values of a column
rename      Rename the columns of CSV data efficiently
replace     Replace patterns in CSV data
reverse     Reverse rows of CSV data
safenames   Modify a CSV's header names to db-safe names
search      Search CSV data with a regex
searchset   Search CSV data with a regex set
snappy      Compress/decompress data using the Snappy algorithm
sortcheck   Check if a CSV is sorted
split       Split CSV data into many files
sqlp        Run a SQL query against several CSVs using the Pola.rs engine
table       Align CSV data into columns
template    Render templates using CSV data
transpose   Transpose rows/columns of CSV data
validate    Validate CSV data for RFC4180-compliance or with JSON Schema
```
