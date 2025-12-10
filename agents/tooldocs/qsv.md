---
title: qsv
docs: https://github.com/dathere/qsv
---

```
Commands:


qsv select
qsv stats
qsv sort
qsv search
qsv count
qsv table
qsv frequency
qsv sample
qsv slice
qsv headers
qsv sniff
qsv dedup
qsv join
qsv split
qsv schema
qsv validate
qsv tojsonl
qsv jsonl
qsv to
qsv rename
qsv replace
qsv apply
qsv index
qsv sqlp
qsv pivotp
qsv joinp
qsv extsort
qsv extdedup

select      Select, re-order, duplicate or drop columns

index       Create CSV index for faster access

apply       Apply series of transformations to a column
behead      Drop header from CSV file
cat         Concatenate by row or column
datefmt     Format date/datetime strings
dedup       Remove redundant rows
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
geocode     Geocodes a location against the Geonames cities database.
geoconvert  Convert between spatial formats & CSV, including GeoJSON, SHP & more
help        Show this usage message
input       Read CSVs w/ special quoting, skipping, trimming & transcoding rules
join        Join CSV files
joinp       Join CSV files using the Pola.rs engine
json        Convert JSON to CSV
jsonl       Convert newline-delimited JSON files to CSV
lens        View a CSV file interactively
luau        Execute Luau script on CSV data
partition   Partition CSV data based on a column value
pivotp      Pivots CSV files using the Pola.rs engine
pro         Interact with the qsv pro API
prompt      Open a file dialog to pick a file
pseudo      Pseudonymise the values of a column
rename      Rename the columns of CSV data efficiently
replace     Replace patterns in CSV data
reverse     Reverse rows of CSV data
safenames   Modify a CSV's header names to db-safe names
search      Search CSV data with a regex
searchset   Search CSV data with a regex set
snappy      Compress/decompress data using the Snappy algorithm
sort        Sort CSV data in alphabetical, numerical, reverse or random order
sortcheck   Check if a CSV is sorted
split       Split CSV data into many files
sqlp        Run a SQL query against several CSVs using the Pola.rs engine
table       Align CSV data into columns
template    Render templates using CSV data
tojsonl     Convert CSV to newline-delimited JSON
to          Convert CSVs to PostgreSQL/XLSX/SQLite/Data Package
transpose   Transpose rows/columns of CSV data
validate    Validate CSV data for RFC4180-compliance or with JSON Schema
```

```bash
# Command help
qsv $COMMAND --help

# Infer delimiter/header/preamble/quote char, record counts, MIME-type detector
qsv sniff data.csv

# Infer field, type, basic (sum, min, max, ...) and advanced stats (cv, nullcount, max_precision, sparsity, ...)
qsv stats data.csv

# Print first five rows
qsv slice -l 5 data.csv | qsv table

# Stats on 10 random rows
qsv sample -n 10 data.csv | qsv stats

# Select columns 1, 3, 4, 5
qsv select 1,3-5
# Select columns ColA, ColC to anything matching ColD, column 6 onwards, not columns 10-11
qsv select ColA,ColC-/ColD/,6-,!10-11

# Sort by ColA (lexical), ColB (numeric, natural order), descending, ignore case
qsv sort --select ColA,ColB --reverse --ignore-case --numeric --natural data.csv

# Show per-column frequency tables
qsv frequency data.csv

# Deduplicate on a column
qsv dedup -s "Email" data.csv

# Regex replace to drop text
qsv apply operations regex_replace --comparand "PATTERN" --replacement "<NULL>" -c cleaned_col "Original Column" data.csv

# Join two CSVs (note: column is repeated)
qsv join "Email" a.csv "Email" b.csv
```

- There is no `--limit` parameter.
- Set delimiter via `--delimiter`, or `QSV_DEFAULT_DELIMITER`, or auto-detect with `QSV_SNIFF_DELIMITER` (not for stdin)
