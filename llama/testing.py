from transformers import AutoTokenizer
from transformers.pipelines.pt_utils import KeyDataset
from tqdm import tqdm
from datasets import Dataset
import numpy as np
import pandas as pd
from sklearn.metrics import confusion_matrix

import transformers
import torch

import re
import random
import string
import time



MODEL = './models/genre-llama-demo'
GENRES = ['sport', 'news', 'game-show', 'horror', 'fantasy', 'western', 'romance', 'family', 'adult', 'documentary', 'drama', 'war', 'action', 'history', 'musical', 'reality-tv', 'talk-show', 'crime', 'comedy', 'animation', 'short', 'sci-fi', 'biography', 'music', 'adventure', 'mystery']

def parse_model_output(result):
    # extract the actual response from the model output
    all_text = result[0]["generated_text"]
    location = all_text.find("[/INST]") + 8
    model_response = all_text[location:]

    # Split on spaces and slashes
    words = re.split(r'[ /\n]+', model_response.lower())
    # Find the first word that is in the GENRE list
    classif = "" # If model didn't return a genre from the list, just use the empty string
    for word in words:
        word = word.strip().translate(str.maketrans("", "", string.punctuation)) # remove punctuation
        if word in GENRES:
            classif = word
            break

    return classif

def get_preds(prompts, base_model):
    """Returns a list of predictions generated by the specified model for the given prompts"""

    print("Testing set size: " + str(len(prompts)))

    # Load the llama model
    tokenizer = AutoTokenizer.from_pretrained(base_model)
    pipeline = transformers.pipeline(
        "text-generation",
        model=base_model,
        torch_dtype=torch.float16,
        device_map="auto",
    )

    results = []
    start = time.time()
    prompts = prompts.copy()

    # Define a list of genres to add to the prompt, if the model was trained with the list
    genres_str = ""
    if base_model.find("list") != -1:
        genres_str = "The genre classes are: " + ", ".join(GENRES) + "."

    # Generate prompts using the same format as in training
    for i in range(len(prompts)):
        messages = [
            {
                "role": "system",
                "content": "You are a classification robot. Your job is to provide genres for movies based on their titles and descriptions."
            + "The user will provide you with a title and a description, and you should simply provide a genre that fits the movie. Do not include any text other than the genre."
            + genres_str,
            },
            {"role": "user", "content": prompts[i]},
        ]
        prompts[i] = tokenizer.apply_chat_template(messages, tokenize=False)

    
    # Create a dataset from the prompts using the huggingface Dataset class
    prompts_dataset = Dataset.from_pandas(pd.DataFrame(prompts))
    
    # Run the prompts through the model to generate predictions
    for result in tqdm(pipeline(
                KeyDataset(prompts_dataset, '0'), # "0" is the name of the column; this was confusing.
                do_sample=True,
                top_k=10,
                top_p=0.9,
                temperature=0.6, # Performs better than lower temperatures, contrary to initial beliefs
                num_return_sequences=1,
                eos_token_id=tokenizer.eos_token_id,
                max_new_tokens=10,
            )):
        #Extract the actual response from the model output
        classif = parse_model_output(result)

        results.append(classif)

    print(
        "Time taken to complete "
        + str(len(results))
        + " samples: "
        + str(time.time() - start)
    )
    return results




#### MAIN CODE ####

prompts = []
completions = []
# Load the dataset from the test file "genredataset/train_data.txt"
with open("./genredataset/test_data_solution.txt", "r") as f:
    # Append data to the prompts from the file
    for line in f.readlines():
        data = line.split(" ::: ")
        prompts.append("Title: " + data[1] + "\nDescription: " + data[3])
        completions.append(data[2])

# Shuffle the order of the prompts and completions
zipped = list(zip(prompts, completions))
random.Random(1993).shuffle(zipped) # instantiate random with a seed for reproducibility
prompts, completions = zip(*zipped)

# Limit the number of prompts and completions to 1000
prompts = list(prompts[:1000])
completions = list(completions[:1000])

# Use the get_preds to actually run the model
predictions = get_preds(prompts, base_model=MODEL)

# Calculate accuracy between predictions and completions
correct = 0
for i in range(len(predictions)):
    print("Prediction: " + predictions[i] + ", completion: " + completions[i])
    if predictions[i] == completions[i]:
        correct += 1

print("Accuracy: " + str(correct / len(predictions)))

# Generate a genre x genre confusion matrix
cm = confusion_matrix(completions, predictions, labels=GENRES)

# Print confusion matrix
print("Confusion Matrix:")
print("       " + "  ".join(f"{cls[:5]:>5}" for cls in GENRES))  # Header row
for i, row in enumerate(cm):
    print(f"{GENRES[i][:5]:>5} " + "  ".join(f"{val:>5}" for val in row))


# Calculate the average precision, recall and F1 score
precision = np.zeros(len(GENRES))
recall = np.zeros(len(GENRES))
f1 = np.zeros(len(GENRES))
for i in range(len(GENRES)):
    precision[i] = cm[i][i] / sum(cm[i]) if sum(cm[i]) > 0 else 0
    recall[i] = cm[i][i] / sum(row[i] for row in cm) if sum(row[i] for row in cm) > 0 else 0
    f1[i] = 2 * precision[i] * recall[i] / (precision[i] + recall[i]) if precision[i] + recall[i] > 0 else 0

# Print the averages of the lists
print("\n\n")
print("Average precision: " + str(np.mean(precision)))
print("Average recall: " + str(np.mean(recall)))
print("Average F1 score: " + str(np.mean(f1)))


print ("\n\n")
# Print the genre most commonly misclassified as each genre, and the percentage of times it was misclassified as that genre
for i, row in enumerate(cm):
    # Calculate row sum, for percentage calculation
    row_sum = sum(row)
    # Exclude the correct classification
    row[i] = 0
    max_val = max(row)
    # Check that the max value is at least 1
    if max_val == 0:
        continue
    # Find the index of the max value (or values, if it's a tie)
    max_index = np.argwhere(row == max_val).flatten()
    for index in max_index:
        print(
            f"{GENRES[i]} most commonly misclassified as {GENRES[index]}: {max_val / row_sum:.2%}"
        )