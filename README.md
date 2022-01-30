# TDA-utils
Collection of helpful python functions on top of `tda-api` python wrapper

## credential file
`credential.py` file needs to contain the following four constants:

| Constant name | Filetype  | Description |
| ------------  | -------   | ----------- |
| `tda_token_path`  | `str` | path to the `token.pickle` file generated by `tda-api`|
| `tda_api_key` |   `str`   | api key from TDA website
| `tda_redirect_uri` | `str` | e.g) `'http://localhost'`
| `tda_accountid`   | `int` | account id from TDA website


