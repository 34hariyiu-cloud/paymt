07:12:27] 🐍 Python dependencies were installed from /mount/src/paymt/requirements.txt using uv.

Check if streamlit is installed

Streamlit is already installed

[07:12:29] 📦 Processed dependencies!




/mount/src/paymt/app.py:97: UserWarning: The argument 'infer_datetime_format' is deprecated and will be removed in a future version. A strict version of it is now the default, see https://pandas.pydata.org/pdeps/0004-consistent-to-datetime-parsing.html. You can safely remove this argument.

  return pd.to_datetime(s, errors="coerce", infer_datetime_format=True)

────────────────────── Traceback (most recent call last) ───────────────────────

  /home/adminuser/venv/lib/python3.13/site-packages/streamlit/runtime/scriptru  

  nner/exec_code.py:129 in exec_func_with_error_handling                        

                                                                                

  /home/adminuser/venv/lib/python3.13/site-packages/streamlit/runtime/scriptru  

  nner/script_runner.py:671 in code_to_exec                                     

                                                                                

  /mount/src/paymt/app.py:272 in <module>                                       

                                                                                

    269 k1, k2, k3 = st.columns(3)                                              

    270 with k1:                                                                

    271 │   st.subheader("Total amount")                                        

  ❱ 272 │   st.markdown(f"**{inr(total_amount)}**")                             

    273 │   st.caption(f"(from {len(fdf)} invoices)")                           

    274 with k2:                                                                

    275 │   st.subheader("Amount paid")                                         

────────────────────────────────────────────────────────────────────────────────

NameError: name 'inr' is not defined
