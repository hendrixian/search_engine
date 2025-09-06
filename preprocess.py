from pyspark.sql import SparkSession
from pyspark.sql.functions import lower, regexp_replace

spark = SparkSession.builder.appName("AcademicPaperPreprocessing").getOrCreate()

# Load CSV
df = spark.read.csv("papers.csv", header=True)

# Simple preprocessing: lowercase and remove punctuation from abstract
df_clean = df.withColumn("abstract_clean", lower(regexp_replace("abstract", "[^a-zA-Z0-9 ]", "")))

df_clean.show(truncate=False)

# Collect to driver for indexing
papers = df_clean.select("id", "title", "authors", "abstract_clean", "pdf_path").toPandas()

spark.stop()
