import arcpy
from arcpy.sa import Float
import pandas as pd
import math
import matplotlib.pyplot as plt


class SmartRaster(arcpy.Raster):

    def __init__(self, raster_path):
        # Initialize the SmartRaster object with the raster path
        super().__init__(raster_path)
        self.raster_path = raster_path
        self.metadata = self._extract_metadata()  # Extract metadata for the raster

    def _extract_metadata(self):
        # Extract metadata such as bounds, dimensions, and pixel type
        desc = arcpy.Describe(self.raster_path)
        extent = desc.extent

        # Define raster bounds using extent
        bounds = [[extent.XMin, extent.YMax],
                  [extent.XMax, extent.YMin]]

        # Get raster dimensions, number of bands, and pixel type
        y_dim = self.height
        x_dim = self.width
        n_bands = self.bandCount
        pixelType = self.pixelType

        # Return metadata as a dictionary
        return {
            "bounds": bounds,
            "x_dim": x_dim,
            "y_dim": y_dim,
            "n_bands": n_bands,
            "pixelType": pixelType
        }

    def calculate_ndvi(self, band4_index=4, band3_index=3):
        """
        Calculate NDVI using the NIR (band 4) and Red (band 3) bands.
        NDVI = (NIR - Red) / (NIR + Red)
        """
        # Initialize a tracker variable to indicate success or failure
        okay = True

        # Initialize the NDVI raster variable to None
        ndvi_raster = None

        try:
            # Load the NIR (band 4) raster using the provided band index
            nir_band = arcpy.Raster(f"{self.raster_path}\\Band_{band4_index}") 

            # Load the Red (band 3) raster using the provided band index
            red_band = arcpy.Raster(f"{self.raster_path}\\Band_{band3_index}")
        except Exception as e:
            # If there is an error loading the bands, set tracker to False and return the error message
            okay = False
            return okay, f"Error retrieving bands: {e}"

        try:
            # Calculate the numerator of the NDVI formula (NIR - Red)
            numerator = Float(nir_band - red_band)

            # Calculate the denominator of the NDVI formula (NIR + Red)
            denominator = Float(nir_band + red_band)

            # Compute the NDVI by dividing the numerator by the denominator
            ndvi_raster = numerator / denominator

            # Return success and the resulting NDVI raster
            return okay, ndvi_raster
        except Exception as e:
            # If there is an error during the NDVI calculation, set tracker to False and return the error message
            okay = False
            return okay, f"Error calculating NDVI: {e}"


# Potential smart vector layer

class SmartVectorLayer:
    def __init__(self, feature_class_path):
        """Initialize with a path to a vector feature class"""
        self.feature_class = feature_class_path
        
        # Check if the feature class exists, raise an error if not
        if not arcpy.Exists(self.feature_class):
            raise FileNotFoundError(f"{self.feature_class} does not exist.")
    
    def summarize_field(self, field):
        """
        Calculate the mean of a specified field in the feature class.
        """
        okay = True  # Tracker variable for success

        try: 
            # Get a list of all fields in the feature class
            existing_fields = [f.name for f in arcpy.ListFields(self.feature_class)]
            
            # Check if the specified field exists
            if field not in existing_fields:
                okay = False
                print(f"The field {field} is not in list of possible fields")
                return False, None
        except Exception as e:
            # Handle errors during field checking
            print(f"Problem checking the fields: {e}")

        try: 
            # Use a SearchCursor to extract values from the specified field
            with arcpy.da.SearchCursor(self.feature_class, [field]) as cursor:
                vals = [row[0] for row in cursor if row[0] is not None and not math.isnan(row[0])]
            
            # Calculate the mean of the field values
            mean = sum(vals) / len(vals)
            return okay, mean
        except Exception as e:
            # Handle errors during mean calculation
            print(f"Problem calculating mean: {e}")
            okay = False
            return okay, None

    def zonal_stats_to_field(self, raster_path, statistic_type="MEAN", output_field="ZonalStat"):
        """
        For each feature in the vector layer, calculates the zonal statistic from the raster
        and writes it to a new field.
        
        Parameters:
        - raster_path: path to the raster
        - statistic_type: type of statistic ("MEAN", "SUM", etc.)
        - output_field: name of the field to create to store results
        """
        okay = True  # Tracker variable for success

        try:
            # Check if the output field already exists
            existing_fields = [f.name for f in arcpy.ListFields(self.feature_class)]
            if output_field not in existing_fields:
                # Add the output field if it doesn't exist
                arcpy.AddField_management(self.feature_class, output_field, "DOUBLE")
            else:
                # If the field exists, return an error message
                okay = False
                error_msg = f"field {output_field} already exists"
                return okay, error_msg
        except Exception as e:
            # Handle errors during field addition
            okay = False
            error_msg = e
            return okay, error_msg

        # Create a temporary table to hold zonal statistics
        temp_table = "in_memory\\temp_zonal_stats"
        if arcpy.Exists(temp_table):
            arcpy.management.Delete(temp_table)
        
        try:
            # Calculate zonal statistics using the specified raster and statistic type
            zone_field = "OBJECTID"
            arcpy.sa.ZonalStatisticsAsTable(
                in_zone_data=self.feature_class,
                zone_field=zone_field,
                in_value_raster=raster_path,
                out_table=temp_table,
                statistics_type=statistic_type
            )
        except Exception as e:
            # Handle errors during zonal statistics calculation
            okay = False
            error_msg = e
            return okay, error_msg

        # Dictionary to store zonal statistics results
        zonal_results = {}
        
        try:
            # Read the zonal statistics results from the temporary table
            table_count = 0
            with arcpy.da.SearchCursor(temp_table, ["OBJECTID_1", statistic_type]) as cursor:
                for row in cursor:
                    zonal_results[row[0]] = row[1]
                    table_count += 1
            print(f"Processed {table_count} zonal stats")
        except Exception as e:
            # Handle errors during table reading
            print(f"Problem reading the zonal results table: {e}")
            okay = False
            return okay, f"Read error: {e}"
        
        print("Joining zonal stats back to Object ID")
        try:
            # Update the feature class with the zonal statistics results
            with arcpy.da.UpdateCursor(self.feature_class, ["OBJECTID", output_field]) as cursor:
                for row in cursor:
                    oid = row[0]
                    if oid in zonal_results:
                        row[1] = zonal_results[oid]
                        cursor.updateRow(row)
        except Exception as e:
            # Handle errors during feature class update
            print(f"Problem updating feature class: {e}")
            okay = False
            error_msg = e
            return okay, error_msg

        # Clean up the temporary table
        arcpy.management.Delete(temp_table)

        print(f"Zonal stats '{statistic_type}' added to field '{output_field}'.")
        return okay, None

    def save_as(self, output_path):
        """
        Save the current vector layer to a new feature class.
        """
        arcpy.management.CopyFeatures(self.feature_class, output_path)
        print(f"Saved to {output_path}")

    def extract_to_pandas_df(self, fields=None):
        """
        Extract the attribute table of the feature class to a pandas DataFrame.
        
        Parameters:
        - fields: list of fields to include in the DataFrame (default: all fields except geometry and OID)
        
        Returns:
        - A tuple (okay, df), where:
          - okay: Boolean indicating success or failure
          - df: pandas DataFrame containing the extracted data (or None if an error occurs)
        """
        okay = True  # Tracker variable for success

        # If no fields are specified, include all fields except geometry and OID
        if fields is None:
            fields = [f.name for f in arcpy.ListFields(self.feature_class) if f.type not in ('Geometry', 'OID')]
        else:
            # Validate user-specified fields against the actual fields in the feature class
            true_fields = [f.name for f in arcpy.ListFields(self.feature_class) if f.type not in ('Geometry', 'OID')]
            disallowed = [user_f for user_f in fields if user_f not in true_fields]
            if len(disallowed) != 0:
                # If invalid fields are provided, print an error message and return failure
                print("Fields given by user are not valid for this table")
                print(disallowed)
                okay = False
                return okay, None
        
        # Include the OID field along with the specified fields
        fields_with_oid = ["OID@"] + fields
        rows = []  # List to store rows extracted from the feature class

        try:
            # Use a SearchCursor to extract rows from the feature class
            with arcpy.da.SearchCursor(self.feature_class, fields_with_oid) as cursor:
                for row in cursor:
                    rows.append(row)
        except Exception as e:
            # Handle errors during row extraction
            print(f"Error reading rows with SearchCursor: {e}")
            okay = False
            return okay, None
        
        try:
            # Define column names for the DataFrame
            col_names = ["OID"] + fields
            
            # Create a pandas DataFrame from the extracted rows
            df = pd.DataFrame(rows, columns=col_names)
            
            # Convert numeric fields to numeric types, coercing errors to NaN
            for field in fields:
                df[field] = pd.to_numeric(df[field], errors='coerce')
            
            # Return success and the resulting DataFrame
            return okay, df
        except Exception as e:
            # Handle errors during DataFrame creation
            print(f"Error creating DataFrame: {e}")
            okay = False
            return okay, None


# Uncomment this when you get to the appropriate block in the scripts
#  file and re-load the functions

class smartPanda(pd.DataFrame):

    # This next bit is advanced -- don't worry about it unless you're 
    # curious.  It has to do with the pandas dataframe
    # being a complicated thing that could be created from a variety
    #   of types, and also that it creates a new dataframe
    #   when it does operations.  The use of @property is called
    #   a "decorator".  The _constructor(self) is a specific 
    #   expectation of Pandas when it does operations.  This just
    #   tells it that when it does an operation, make the new thing
    #   into a special smartPanda type, not an original dataframe. 

    @property
    def _constructor(self):
        return smartPanda
    
    # here, just set up a method to plot and to allow
    #   the user to define the min and max of the plot. 


    def scatterplot(self, x_field, y_field, title=None, 
                    x_min=None, x_max=None, 
                    y_min=None, y_max=None):
        """Make a scatterplot of two columns, with validation."""

        # Validate
        for field in [x_field, y_field]:
            if field not in self.columns:
                raise ValueError(f"Field '{field}' not found in DataFrame columns.")

        # filter the range
        df_to_plot = self
        if x_min is not None:
            df_to_plot = df_to_plot[df_to_plot[x_field] >= x_min]
        if x_max is not None:
            df_to_plot = df_to_plot[df_to_plot[x_field] <= x_max]
        if y_min is not None:
            df_to_plot = df_to_plot[df_to_plot[y_field] >= y_min]
        if y_max is not None:
            df_to_plot = df_to_plot[df_to_plot[y_field] <= y_max]



        # Proceed to plot
        plt.figure(figsize=(8,6))
        plt.scatter(df_to_plot[x_field], df_to_plot[y_field])
        plt.xlabel(x_field)
        plt.ylabel(y_field)
        plt.title(title if title else f"{y_field} vs {x_field}")
        plt.grid(True)
        plt.show()


    def mean_field(self, field):
        """Get mean of a field, ignoring NaN."""
        return self[field].mean(skipna=True)

    def save_scatterplot(self, x_field, y_field, outfile, title=None, 
                    x_min=None, x_max=None, 
                    y_min=None, y_max=None):
        """Make a scatterplot of two columns, with validation."""
   
        # Validate
        for field in [x_field, y_field]:
            if field not in self.columns:
                raise ValueError(f"Field '{field}' not found in DataFrame columns.")
        

        # filter the range
        df_to_plot = self
        if x_min is not None:
            df_to_plot = df_to_plot[df_to_plot[x_field] >= x_min]
        if x_max is not None:
            df_to_plot = df_to_plot[df_to_plot[x_field] <= x_max]
        if y_min is not None:
            df_to_plot = df_to_plot[df_to_plot[y_field] >= y_min]
        if y_max is not None:
            df_to_plot = df_to_plot[df_to_plot[y_field] <= y_max]

        # Proceed to plot
        plt.figure(figsize=(8,6))
        plt.scatter(df_to_plot[x_field], df_to_plot[y_field])
        plt.xlabel(x_field)
        plt.ylabel(y_field)
        plt.title(title if title else f"{y_field} vs {x_field}")
        plt.grid(True)
        plt.savefig(outfile)
        plt.close()

    def plot_from_file(self, csv_control_file_path):
        # This method reads a CSV control file and uses it to create a scatterplot
        # based on the parameters specified in the file, then saves the plot to a file.

        # First, use pandas to read the .csv file. The file should have two columns:
        # 'Param' and 'Value'. The 'Param' column contains the names of the parameters
        # (e.g., "x_field"), and the 'Value' column contains their corresponding values.
        # Required parameters:
        #   - x_field: string (name of the x-axis field)
        #   - y_field: string (name of the y-axis field)
        #   - outfile: string (path to the output graphics file)
        # Optional parameters:
        #   - x_min, x_max, y_min, y_max: numeric (range limits for the axes)

        try: 
            # Read the CSV file into a pandas DataFrame
            params = pd.read_csv(csv_control_file_path)
        except Exception as e:
            # Handle errors during file reading
            print(f"Problem reading the {csv_control_file_path}")
            return False
        
        try:
            # Convert the DataFrame into a dictionary with 'Param' as keys and 'Value' as values
            param_dict = {k.strip(): v for k, v in zip(params['Param'], params['Value'])}
        except Exception as e:
            # Handle errors during dictionary creation
            print(f"Problem setting up dictionary: {e}")
            return False

        # Check that all required parameters are present in the dictionary
        required_params = ["x_field", "y_field", "outfile"]
        missing = [m for m in required_params if m not in param_dict.keys()]
        if missing:
            # If any required parameters are missing, print an error message and return
            print("The param file needs to have these additional parameters")
            print(missing)
            return False

        # Add default values (None) for optional parameters if they are not provided
        optional_params = ["x_min", "x_max", "y_min", "y_max"]
        for p in optional_params:
            val = param_dict.get(p, None)
            try:
                # Convert the value to a float if it is not None or an empty string
                param_dict[p] = float(val) if val not in [None, 'None', ''] else None
            except (ValueError, TypeError):
                # Handle errors during conversion and set the value to None
                print(f"Could not convert {p}='{val}' to float.")
                param_dict[p] = None

        # Create and save the scatterplot using the parameters from the dictionary
        try:
            self.save_scatterplot(param_dict['x_field'], 
                                  param_dict['y_field'], 
                                  param_dict['outfile'], 
                                  x_min=param_dict['x_min'], 
                                  x_max=param_dict['x_max'],
                                  y_min=param_dict['y_min'],
                                  y_max=param_dict['y_max'])
            print(f"Scatterplot saved to {param_dict['outfile']}")
            return True  # Indicate success
        except Exception as e:
            # Handle errors during scatterplot creation or saving
            print(f"Problem saving the scatterplot: {e}")
            return False

        
            
        
        








