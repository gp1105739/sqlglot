import typing as t
from copy import copy

from sqlglot import expressions as exp

if t.TYPE_CHECKING:
    from sqlglot.dataframe.sql.dataframe import DataFrame
    from sqlglot.dataframe.sql.session import SparkSession


class DataFrameReader:
    def __init__(self, spark: "SparkSession"):
        self.spark = spark

    def table(self, table_name: str) -> "DataFrame":
        from sqlglot.dataframe.sql.dataframe import DataFrame

        return DataFrame(self.spark, exp.Select().from_(table_name).select("*"),
                         branch_id=self.spark._random_branch_id,
                         sequence_id=self.spark._random_sequence_id)._convert_leaf_to_cte()


class DataFrameWriter:
    def __init__(self, df: "DataFrame", spark: "SparkSession" = None, mode: str = None):
        self._df = df
        self._spark = spark or df.spark
        self._mode = mode

    def copy(self, **kwargs) -> "DataFrameWriter":
        kwargs = {
            **{k: copy(v) for k, v in vars(self).copy().items()},
            **kwargs
        }
        return DataFrameWriter(**{k.replace("_", ""): v for k, v in kwargs.items()})

    def sql(self, **kwargs) -> str:
        return self._df.sql(**kwargs)

    def mode(self, saveMode: t.Optional[str]) -> "DataFrameWriter":
        return self.copy(_mode=saveMode)

    def insertInto(self, tableName: str, overwrite: t.Optional[bool] = None) -> "DataFrameWriter":
        expression_without_cte = self._df.expression.copy()
        expression_without_cte.set("with", None)
        insert_expression = exp.Insert(**{
            "this": self._get_table_expression_from_name(tableName),
            "expression": expression_without_cte,
            "overwrite": overwrite,
            "with": self._df.expression.args.get("with")
        })
        return self.copy(_df=self._df.copy(expression=insert_expression))

    def saveAsTable(self,
                    name: str,
                    format: t.Optional[str] = None,
                    mode: t.Optional[str] = None):
        if format is not None:
            raise NotImplementedError("Providing Format in the save as table is not supported")
        exists, replace, mode = None, None, mode or str(self._mode)
        if mode == "append":
            return self.insertInto(name)
        if mode == "ignore":
            exists = True
        if mode == "overwrite":
            replace = True
        ctas_expression = exp.Create(
            this=self._get_table_expression_from_name(name),
            kind="TABLE",
            expression=self._df.expression,
            exists=exists,
            replace=replace,
        )
        return self.copy(_df=self._df.copy(expression=ctas_expression))

    def _get_table_expression_from_name(self, name: str):
        reference = name.split(".")
        catalog, db, table_name = ([None] * (3 - len(reference))) + reference
        return exp.Table(
            this=exp.Identifier(this=table_name),
            db=exp.Identifier(this=db) if db is not None else None,
            catalog=exp.Identifier(this=catalog) if catalog is not None else None,
        )
