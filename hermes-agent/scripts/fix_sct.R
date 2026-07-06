# Fix: add before SCTransform
options(future.globals.maxSize = 4000 * 1024^2)  # 4GB
# Or disable parallel
library(future)
plan(sequential)
