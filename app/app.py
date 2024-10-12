import streamlit as st
st.set_page_config(layout='wide')
import os,sys
import pandas as pd
import os,openai
import pandas as pd
from typing import List, Tuple
import langchain
from langchain_community.utilities import SQLDatabase
from langchain.chains import create_sql_query_chain
from langchain_community.tools.sql_database.tool import QuerySQLDataBaseTool
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from operator import itemgetter
from sqlalchemy import create_engine
from langchain_community.agent_toolkits import create_sql_agent
from langchain_openai import ChatOpenAI
langchain.debug = False
from datetime import datetime  # Import datetime for timestamp handling
import logging
from dotenv import load_dotenv
from mysql import connector

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Load environment variables
load_dotenv()

# Get the variables from the environment
load_dotenv(dotenv_path=".env.dbdetails")
db_user = os.getenv('DB_USER')
db_password = os.getenv('DB_PASSWORD')
db_host = os.getenv('DB_HOST')  ## Docker dbhost is not connecting via jupyter  
db_port = os.getenv('DB_PORT')
db_name = os.getenv('DB_NAME')

# Set the title of the page
st.title("CryptoCurrency trend analysis powered by GPT-3.5-turbo")

mysql_uri = f"mysql+mysqlconnector://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"

# Define MySQL URI
engine = create_engine(mysql_uri)

# Create SQLDatabase object from URI
db = SQLDatabase.from_uri(mysql_uri)
print(db.dialect)

llm = ChatOpenAI(model="gpt-3.5-turbo", temperature=1)
agent_executor = create_sql_agent(llm, db=db, agent_type="openai-tools",return_intermediate_steps=False, return_direct=True)


def create_db_table(combined_df):
    # Create table in MySQL database
    combined_df.to_sql("crypto_data", engine, index=False, if_exists="append")
    
    # Test if table is created
    try:
        result = pd.read_sql_table("crypto_data", engine)
        print("\nTable 'crypto_data' exists and has shape:", result.shape)
    except Exception as e:
        print("\nError:", str(e))
        

def get_answer_from_sql(user_query):
    answer_prompt = PromptTemplate.from_template(
        """Given the following user question,corresponding SQL query, and SQL result, 
        answer the user question in upto 4 lines from the data provided in the SQL result.

        Question: {question}
        SQL Query: {query}
        SQL Result: {result}
        Answer: """
    )

    execute_query = QuerySQLDataBaseTool(db=db)
    write_query = create_sql_query_chain(llm, db)
    answer = answer_prompt | llm | StrOutputParser()

    chain = (
        RunnablePassthrough.assign(query=write_query).assign(
            result=itemgetter("query") | execute_query 
        )
        | answer_prompt
        | llm
        | StrOutputParser()
    )

    try:
        response = chain.invoke({"question": user_query})
        logging.info("Chain invoked successfully.")
        return response
    except Exception as e:
        logging.error(f"An error occurred: {e}")


def chat_with_csv(input_text):
    try:
        response = get_answer_from_sql(input_text)
        return response
    except Exception as e:
        # Show any errors that occur during the API call
        st.error(f"Error: {e}")
        return None
        
def prepare_data(combined_df):
    combined_df = combined_df.rename(columns={
    'cryptocurrency': 'Symbol'
    }).astype({
    'Date': 'datetime64[ns]',
    'Symbol': 'object'
    })
    
    
    # Remove commas from columns and then convert to float
    combined_df['Open'] = pd.to_numeric(combined_df['Open'].replace(',', '', regex=True), errors='coerce')
    combined_df['Close'] = pd.to_numeric(combined_df['Close'].replace(',', '', regex=True), errors='coerce')
    combined_df['Low'] = pd.to_numeric(combined_df['Low'].replace(',', '', regex=True), errors='coerce')
    combined_df['High'] = pd.to_numeric(combined_df['High'].replace(',', '', regex=True), errors='coerce')

    print("\nCombined DataFrame shape:", combined_df.shape)
    return combined_df
    

# File uploader widget to accept CSV files
input_csv = st.file_uploader("Upload your CSV file, include a column for cryptocurrency (include BTC for bitcoin or eth for ethereum)", type=['csv'])

if input_csv is not None:
    # Create two columns for layout
    col1, col2 = st.columns([1, 1])

    with col1:
        st.info("CSV Uploaded Successfully")
        # Read the uploaded CSV file into a DataFrame
        data = pd.read_csv(input_csv)
        
        combined_df = prepare_data(data)
        create_db_table(combined_df)
        # Display the DataFrame in a container
        st.dataframe(data, use_container_width=True)

    with col2:
        st.info("Chat Below")
        # Text area for the user to enter their query
        input_text = st.text_area("Enter your query")

        if input_text:
            # Button to initiate the chat
            if st.button("Chat with CSV"):
                st.info("Your Query: " + input_text)
                # Call the function to chat with the CSV data
                result = chat_with_csv(input_text)
                if result is not None:
                    # Display the chat result
                    st.success(result)