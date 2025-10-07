from fastapi import APIRouter, HTTPException
from ..schemas import SQLRequest, SQLResponse
from ...parser.sql_parser import parser
from ...parser.sql_transformer import SQLTransformer
from ...app.engine import get_engine

router = APIRouter()
_transformer = SQLTransformer()

@router.post("/sql", response_model=SQLResponse)
def run_sql(req: SQLRequest):
    try:
        tree = parser.parse(req.sql)
        ast_dict = _transformer.transform(tree)
        result = get_engine().execute(ast_dict)
        return SQLResponse(**result, ok=True)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
