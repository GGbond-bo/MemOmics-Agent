#!/usr/bin/env Rscript
# 持久 R kernel worker（P0-1）：stdin/stdout 行式 JSON 协议（与 Python worker 一致）
# 请求: {"id":"1","code":"..."}
# 响应: {"id":"1","stdout":"...","stderr":"...","error":null|"..."}
# 命名空间常驻 globalenv()，跨请求保留变量/模块状态。
# 多语句按序执行，最后一个表达式若可见则回显（Jupyter cell 语义）。
suppressMessages(library(jsonlite))

run <- function() {
  con <- file("stdin", open = "r")
  on.exit(close(con))
  while (TRUE) {
    line <- readLines(con, n = 1, warn = FALSE)
    if (length(line) == 0 || is.na(line) || nchar(line) == 0) next
    req <- tryCatch(fromJSON(line, simplifyVector = TRUE), error = function(e) NULL)
    if (is.null(req) || is.null(req$id)) next
    rid <- req$id
    code <- req$code
    out <- ""
    err_txt <- ""
    error_msg <- NULL
    tryCatch({
      captured <- capture.output({
        exprs <- tryCatch(parse(text = code), error = function(e) stop(e))
        n <- length(exprs)
        if (n > 0) {
          if (n > 1) for (i in seq_len(n - 1)) eval(exprs[i], envir = globalenv())
          res <- withVisible(eval(exprs[n], envir = globalenv()))
          if (res$visible && !is.null(res$value)) print(res$value)
        }
      }, type = "output")
      if (length(captured) > 0) out <- paste0(paste(captured, collapse = "\n"), "\n")
    }, error = function(e) {
      error_msg <<- conditionMessage(e)
      err_txt <<- conditionMessage(e)
    })
    resp <- list(id = rid, stdout = out, stderr = err_txt, error = error_msg)
    cat(toJSON(resp, auto_unbox = TRUE, force = TRUE), "\n")
    flush(stdout())
  }
}

run()
