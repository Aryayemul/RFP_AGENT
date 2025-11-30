# master_agent.py

from sales_agent import run_sales_node
from technical_agent import run_technical_agent
from pricing_agent import run_pricing_agent

def main():
    print("=== MASTER AGENT STARTED ===")

    # 1. Sales Agent
    
    rfp_urls = [
     "https://www.tcil.net.in/tender/pdf/24e1381_1.pdf",
     "https://mkp.gem.gov.in/catalog_data/catalog_support_document/buyer_documents/964208/54/78/703/CatalogAttrs/SpecificationDocument/2024/1/22/specifications_of_copper_cables_2024-01-22-15-20-17_380f50986d0879644a51cbad3392c672.pdf"
    ]
    rfp_summary = run_sales_node(rfp_urls)
    print("start")
    print(rfp_summary)
    # 2. Technical Agent
    technical_output = run_technical_agent(rfp_summary)

    # 3. Pricing Agent
    pricing_output = run_pricing_agent(technical_output)

    print("\n=== FINAL CONSOLIDATED OUTPUT ===")
    print(pricing_output)

    print("=== MASTER AGENT FINISHED ===")


if __name__ == "__main__":
    main()
