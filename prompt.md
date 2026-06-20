⏺ ## Background                                                                                                                                                        
                                                                                                                                                                     
  I am building an insurance industry knowledge base system on Azure.                                                                                                  
  The current task is to extend an existing initialized codebase with the features described below.
  All generated code must match the existing codebase in style, structure, and naming conventions.                                                                     
                                                                                                                                                                       
  ## Existing Infrastructure                                                                                                                                           
                                                                                                                                                                       
  - Azure Blob Storage: stores raw files (PDF, Word, Excel, images). Files are already in Blob — there is no upload flow.                                              
  - Azure AI Search: managed via Terraform, existing initialization codebase already in place.
  - Azure OpenAI: used for Embedding and final response generation.                                                                                                    
  - Azure AI Agent: used for orchestrating retrieval and generation.                                                                                                   
                                                                                                                                                                       
  ## Skillset Pipeline Overview                                                                                                                                        
                                                                                                                                                                       
  All files go through the following pipeline:                                                                                                                         
   
  PDF / Word / Image:                                                                                                                                                  
    Blob → Document Intelligence Layout Skill → Data Cleaning Custom Skill → Text Split Skill → Embedding Skill → Index                                              
                                                                                                                                                                       
  Excel:
    Blob → Excel Custom Skill → Data Cleaning Custom Skill → Text Split Skill → Embedding Skill → Index                                                                
                                                                                                                                                                       
  ## Requirements
                                                                                                                                                                       
  ### 1. Excel Custom Skill (Azure Function)                                                                                                                         

  Trigger: AI Search Indexer monitors Blob Storage. When an Excel file is detected, it invokes this Custom Skill.                                                      
   
  Processing logic:                                                                                                                                                    
  - Accept the standard Custom Skill input format (values array)                                                                                                     
  - Parse Excel files — must handle multiple sheets, merged cells, and multi-level headers                                                                             
  - Convert each row into a natural language description in the content field                                                                                          
    e.g. "XX Medical Insurance covers bone fractures, with a maximum reimbursement limit of 50,000 CNY."                                                               
  - Each row in each sheet is output as an independent record                                                                                                          
  - Return the standard Custom Skill output format                                                                                                                     
                                                                                                                                                                       
  Output fields per record:                                                                                                                                            
  - content: natural language description text                                                                                                                       
  - source_blob_path: original file path in Blob Storage                                                                                                               
  - source_file_name: file name
  - sheet_name: source sheet name                                                                                                                                      
  - doc_type: fixed value "excel"                                                                                                                                      
  - product_name: extracted from content if identifiable, otherwise empty string
                                                                                                                                                                       
  ### 2. Data Cleaning Custom Skill (Azure Function)                                                                                                                 
                                                                                                                                                                       
  Applies to all file types after Document Intelligence or Excel Custom Skill parsing.                                                                                 
   
  Cleaning logic for PDF / Word / Image:                                                                                                                               
  - Remove headers and footers (company name, page numbers, dates)                                                                                                   
  - Remove table of contents pages
  - Normalize table content extracted by Document Intelligence
    (remove excessive whitespace, fix column separators)
  - Remove watermark text                                                                                                                                              
  - Remove consecutive blank lines and whitespace
  - Re-associate clause numbers with their content                                                                                                                     
    (critical for insurance documents where clause IDs and body text are often separated)                                                                            
  - Merge cross-page chunks that belong to the same clause
                                                                                                                                                                       
  Cleaning logic for Excel (after Excel Custom Skill):
  - Remove records where content is empty or contains only formatting characters                                                                                       
  - Normalize numeric values (remove currency symbols, unify units)                                                                                                  
  - Strip leading/trailing whitespace from all text fields
  - Deduplicate records with identical content across sheets                                                                                                           
   
  Output fields: same as input, with content replaced by cleaned text.                                                                                                 
  Add a field: cleaning_notes (list of transformations applied, for debugging)                                                                                       

  ### 3. AI Search Index Schema                                                                                                                                        
   
  Required fields:                                                                                                                                                     
  - id (key)                                                                                                                                                         
  - content (searchable, used for vectorization)
  - content_vector (vector field, dimensions must match Azure OpenAI Embedding model)                                                                                  
  - source_blob_path (filterable)                                                                                                                                      
  - source_file_name (filterable)                                                                                                                                      
  - page_number (filterable, used for PDF)                                                                                                                             
  - sheet_name (filterable, used for Excel)                                                                                                                            
  - doc_type (filterable): pdf / word / excel / image                                                                                                                  
  - product_name (filterable)
  - last_updated (filterable)                                                                                                                                          
  - cleaning_notes (retrievable, for debugging)                                                                                                                      
                                                                                                                                                                       
  ### 4. Skillset Definition                                                                                                                                           
   
  Include the following skills in order:                                                                                                                               
                                                                                                                                                                     
  For PDF / Word / Image:
  - Built-in: Document Intelligence Layout Skill (handles PDF, Word, image OCR)
  - Custom Skill: Data Cleaning Skill                                                                                                                                  
  - Built-in: Text Split Skill (chunking, chunk size consistent with existing config)
  - Built-in: Azure OpenAI Embedding Skill                                                                                                                             
                                                                                                                                                                     
  For Excel:                                                                                                                                                           
  - Custom Skill: Excel Parsing Skill                                                                                                                                
  - Custom Skill: Data Cleaning Skill                                                                                                                                  
  - Built-in: Text Split Skill
  - Built-in: Azure OpenAI Embedding Skill                                                                                                                             
                                                                                                                                                                     
  Routing logic:                                                                                                                                                       
  - Excel files (.xlsx, .xls) → Excel Custom Skill → Data Cleaning Custom Skill
  - All other file types → Document Intelligence Layout Skill → Data Cleaning Custom Skill                                                                             
                                                                                                                                                                     
  ### 5. Indexer Configuration                                                                                                                                         
                                                                                                                                                                     
  - Data source: Azure Blob Storage                                                                                                                                    
  - Incremental update: based on file last-modified time
  - Field mappings: Skillset output fields → Index fields                                                                                                              
                                                                                                                                                                       
  ### 6. Azure AI Agent Tools
                                                                                                                                                                       
  Tool 1: search_knowledge_base(query: str) -> str                                                                                                                   
  - Calls AI Search using hybrid search (vector + keyword + Semantic Reranker)
  - Returns retrieved content along with source metadata
    (source_blob_path, source_file_name, page_number, sheet_name)                                                                                                      
   
  Tool 2: generate_sas_url(blob_path: str, expiry_hours: int = 24) -> str                                                                                              
  - Uses azure-storage-blob SDK to generate a time-limited SAS Token URL for a given Blob path                                                                       
  - Returns the full accessible URL                                                                                                                                    
                                                                                                                                                                     
  ### 7. Final Response Format                                                                                                                                         
   
  The Agent's response must end with a source reference section in the following format:                                                                               
                                                                                                                                                                     
  Reference: {source_file_name} ({page_number or sheet_name})
  Link: {sas_url} (valid for 24 hours)