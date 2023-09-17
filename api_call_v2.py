import requests
import pandas as pd
from io import StringIO
import re
import numpy as np
import zipcodes
import math
from geopy.distance import geodesic



def get(condition, zipcode, max_distance):
    """
    making the api call
    """
    zipcode_info = zipcodes.matching(zipcode)[0]
    lat, long = zipcode_info["lat"], zipcode_info["long"]
    headers = {
    'accept': 'application/json',
    }
    params = {
        'format': 'csv',
        'query.cond': condition,
        'filter.overallStatus': 'NOT_YET_RECRUITING,RECRUITING',
        'postFilter.geo': f'distance({lat},{long},{max_distance}mi)',
        # 'fields': 'NCT Number,Study Title,Study URL,Acronym,Study Status,Brief Summary,Study Results,Conditions,Interventions,Primary Outcome Measures,Secondary Outcome Measures,Other Outcome Measures,Sponsor,Collaborators,Sex,Age,Phases,Enrollment,Funder Type,Study Type,Study Design,Other IDs,Start Date,Primary Completion Date,Completion Date,First Posted,Results First Posted,Last Update Posted,Locations,Study Documents',
        'sort': '@relevance',
        'pageSize': '20',
    }
    response = requests.get('https://clinicaltrials.gov/api/v2/studies', params=params, headers=headers)
    csv_content = response.content.decode('utf-8')
    return pd.read_csv(StringIO(csv_content))


def get_loc(df):
    """
    spliting location information from api call
    making a dataframe with NCT Number and each parsed location
    """
    #making the dictionary to make a dataframe later
    wanted_cols = ["NCT Number", "Place", "City", "State", "Zipcode", "Country"]
    out = {col: [] for col in wanted_cols}
    
    #iterate through the rows
    for i, row in df.iterrows():
        #splitting all the locations, then split each location into its parts
        splitted_locs = [loc.split(",") for loc in row["Locations"].split("|")]
        
        #iterate through each location
        for loc in splitted_locs:
            loc = [item.strip(" ") for item in loc]
            
            #only look in America
            if loc[-1] != "United States":
                continue

            #handling weird cases
            if len(loc) == 3:
                #only have state, zipcode, and country
                loc = [None] + loc[0:2] + [None] + [loc[-1]]
            elif len(loc) == 4:
                #missing zipcode
                loc = loc[:-1] + [None] + loc[-1:]
            elif len(loc) == 6:
                #accidentally split name of place when setting delimiter to ,
                loc[0] = loc[0] + ", " + loc.pop(1)
                #API repeat city and state
            elif len(loc) == 7:
                loc = loc[0:1] + loc[3:]

            assert len(loc) == 5, f"len loc is not five {loc}"

            for col, new_thing in zip(wanted_cols, [row["NCT Number"]] + loc):
                out[col].append(new_thing)


    out = pd.DataFrame(out)
    return out[out['Zipcode'].notna()]

    





allowed_characters_pattern = re.compile(r'1234567890-')
def filter_zipcodes_within_radius(df, target_zip, radius_miles):
    target_location = zipcodes.matching(target_zip)
    if not target_location:
        print(f"ZIP code {target_zip} not found.")
        return pd.DataFrame()

    target_lat = target_location[0]['lat']
    target_lon = target_location[0]['long']

    def calculate_distance(row):
        row_zip = row['Zipcode']
        if len(row_zip) not in (5, 10) and not bool(allowed_characters_pattern.match(row_zip)):
            return None
        row_location = zipcodes.matching(row_zip)
        if not row_location:
            return None
        # print('hi!!')
        row_lat = row_location[0]['lat']
        row_lon = row_location[0]['long']

        distance = geodesic((target_lat, target_lon), (row_lat, row_lon)).miles
        return distance

    df['Distance'] = df.apply(calculate_distance, axis=1)

    filtered_df = df[df['Distance'] <= int(radius_miles)].copy()
    return filtered_df


def splitting(x):
    if not pd.isna(x):
        return x.split("|")
    return x


#defaults
condition = "heart disease"
target_zip = "10027" #remember to clip to 5 digits
max_distance = "50" #miles
num_out = 5

out = {}
def trial_api_call(condition=condition, zipcode=target_zip, max_distance=max_distance, num_out=num_out):
    """
    over arching function that call other functions
    given the above parameters, return top num_out clinical trials
    """
    #type casting for later functions
    max_distance, zipcode = str(max_distance), str(zipcode)
    #doing the actual api call
    df = get(condition, zipcode, max_distance)

    #cleaning up the data frame
    #splitting by |
    for col in ("Conditions", "Interventions", "Other IDs", \
                "Primary Outcome Measures", "Secondary Outcome Measures",\
                "Other Outcome Measures", "Study Design"):
        df[col] = df[col].apply(splitting)

    #type cast into datetime
    for col in ("Start Date", "Primary Completion Date",\
                "Completion Date", "First Posted", \
                "Results First Posted", "Last Update Posted"):
        df[col] = pd.to_datetime(df[col])

    #parse the location into a separate df
    loc_df = get_loc(df)
    out['loc_df'] = loc_df
    #filter the location to be within target radius
    filtered_loc_df = filter_zipcodes_within_radius(loc_df, zipcode, max_distance)
    out["filtered_loc_df"] = filtered_loc_df
    #merged back to original df but only the locations that we want
    df = filtered_loc_df.merge(df, how="left", on="NCT Number", )
    out['df'] = df
    #sorting to get closest locations
    df.sort_values("Distance", ascending=True, inplace=True)

    #temp output, to be better with a score model
    return df.iloc[:num_out, :]

    #picking out conditions
    conditions = {}
    for i, row in df.iterrows():
        for condition in row["Conditions"]:
            conditions[condition] = conditions.get(condition, 0) + 1

    conditions_df = pd.DataFrame({"Condition": [k for k in conditions.keys()],
                                "Occurence": [v for v in conditions.values()]})
        
    conditions_df.sort_values("Occurence", ascending=False)