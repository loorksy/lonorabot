from typing import Literal


def normalize_retcode(code: str | int | None) -> Literal["confirmed", "failed", "ambiguous"]:
    value = str(code) if code is not None else "unknown"
    confirmed = {
        "ERR_NO_ERROR",
        "0",
        "TRADE_RETCODE_DONE",
        "TRADE_RETCODE_DONE_PARTIAL",
        "TRADE_RETCODE_PLACED",
        "TRADE_RETCODE_NO_CHANGES",
        "10008",
        "10009",
        "10010",
        "10025",
    }
    rejected = {
        "3",
        "5",
        "7",
        "8",
        "64",
        "65",
        "129",
        "130",
        "131",
        "132",
        "133",
        "134",
        "135",
        "136",
        "138",
        "140",
        "141",
        "145",
        "147",
        "148",
        "149",
        "150",
        "10004",
        "10006",
        "10007",
        "10013",
        "10014",
        "10015",
        "10016",
        "10017",
        "10018",
        "10019",
        "10020",
        "10021",
        "10022",
        "10024",
        "10026",
        "10027",
        "10028",
        "10029",
        "10030",
        "10032",
        "10033",
        "10034",
        "10035",
        "10036",
        "10038",
        "10039",
        "10040",
        "10041",
        "10042",
        "10043",
        "10044",
        "10045",
        "10046",
    }
    if value in confirmed:
        return "confirmed"
    mt4_rejected = {
        "ERR_INVALID_TRADE_PARAMETERS",
        "ERR_OLD_VERSION",
        "ERR_NOT_ENOUGH_RIGHTS",
        "ERR_TOO_FREQUENT_REQUESTS",
        "ERR_ACCOUNT_DISABLED",
        "ERR_INVALID_ACCOUNT",
        "ERR_INVALID_PRICE",
        "ERR_INVALID_STOPS",
        "ERR_INVALID_TRADE_VOLUME",
        "ERR_MARKET_CLOSED",
        "ERR_TRADE_DISABLED",
        "ERR_NOT_ENOUGH_MONEY",
        "ERR_PRICE_CHANGED",
        "ERR_OFF_QUOTES",
        "ERR_REQUOTE",
        "ERR_LONG_POSITIONS_ONLY_ALLOWED",
        "ERR_TOO_MANY_REQUESTS",
        "ERR_TRADE_MODIFY_DENIED",
        "ERR_TRADE_EXPIRATION_DENIED",
        "ERR_TRADE_TOO_MANY_ORDERS",
        "ERR_TRADE_HEDGE_PROHIBITED",
        "ERR_TRADE_PROHIBITED_BY_FIFO",
    }
    if (
        value in rejected
        or value in mt4_rejected
        or value.removeprefix("TRADE_RETCODE_")
        in {
            "REQUOTE",
            "REJECT",
            "CANCEL",
            "INVALID",
            "INVALID_VOLUME",
            "INVALID_PRICE",
            "INVALID_STOPS",
            "TRADE_DISABLED",
            "MARKET_CLOSED",
            "NO_MONEY",
            "PRICE_CHANGED",
            "PRICE_OFF",
            "INVALID_EXPIRATION",
            "TOO_MANY_REQUESTS",
            "SERVER_DISABLES_AT",
            "CLIENT_DISABLES_AT",
            "LOCKED",
            "FROZEN",
            "INVALID_FILL",
            "ONLY_REAL",
            "LIMIT_ORDERS",
            "LIMIT_VOLUME",
            "INVALID_ORDER",
            "POSITION_CLOSED",
            "INVALID_CLOSE_VOLUME",
            "CLOSE_ORDER_EXIST",
            "LIMIT_POSITIONS",
            "REJECT_CANCEL",
            "LONG_ONLY",
            "SHORT_ONLY",
            "CLOSE_ONLY",
            "FIFO_CLOSE",
            "HEDGE_PROHIBITED",
        }
    ):
        return "failed"
    return "ambiguous"


def normalize_response(
    string_code: str | None, numeric_code: int | None
) -> Literal["confirmed", "failed", "ambiguous"]:
    named, numbered = normalize_retcode(string_code), normalize_retcode(numeric_code)
    if named != "ambiguous" and numbered != "ambiguous" and named != numbered:
        return "ambiguous"
    return named if named != "ambiguous" else numbered
