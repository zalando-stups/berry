package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"io/ioutil"
	"log"
	"os"
	"os/user"
	"strconv"
	"time"

	"github.com/awslabs/aws-sdk-go/aws"
	"github.com/awslabs/aws-sdk-go/service/s3"
	"github.com/sarnowski/mitigation"
)

const (
	mintKeyFormat      = "apps/%s/%s"
	credentialsFile    = "credentials.json"
	credentialsTmpFile = "credentials.json.tmp"
)

var (
	mintBucket     = flag.String("mint-bucket", "", "The S3 bucket, where mint stores all credentials.")
	appId          = flag.String("application-id", "", "The application ID of Kio for which to retrieve credentials.")
	localDir       = flag.String("local-directory", "", "The local directory, where the credentials will be stored.")
	localUser      = flag.String("local-user", "", "The local user which needs to read the credentials.")
	updateInterval = flag.Int("update-interval", 60, "Update interval in seconds.")

	emptyString = ""
)

type CredentialsData struct {
	ApplicationUsername string `json:"application_username"`
	ClientId            string `json:"client_id"`
}

func requireFlag(flagName string, flagValue *string) {
	if *flagValue == "" {
		panic(fmt.Sprintf("flag -%s is required. see help (-h) for more information", flagName))
	}
}

func main() {
	flag.Parse()

	requireFlag("mint-bucket", mintBucket)
	requireFlag("application-id", appId)
	requireFlag("local-directory", localDir)
	requireFlag("local-user", localUser)

	realDir := localDir
	if mitigation.CanActivate() {
		localUserData, err := user.Lookup(*localUser)
		if err != nil {
			panic(err)
		}

		uid, _ := strconv.Atoi(localUserData.Uid)
		gid, _ := strconv.Atoi(localUserData.Gid)

		mitigation.Activate(uid, gid, *localDir)
		localDir = &emptyString
	} else {
		log.Println("Cannot activate mitigation techniques. Make sure berry runs as root or with the least possible privileges.")
	}

	localFile := fmt.Sprintf("%s/%s", *localDir, credentialsFile)
	localTmpFile := fmt.Sprintf("%s/%s", *localDir, credentialsTmpFile)
	mintKey := fmt.Sprintf(mintKeyFormat, *appId, credentialsFile)

	log.Printf("Berry starts to fetch credentials for %s from %s/%s to %s every %d seconds.", *appId, *mintBucket, mintKey, *realDir, *updateInterval)
	client := s3.New(&aws.Config{})

	firstLoop := true
	for {
		if firstLoop {
			firstLoop = false
		} else {
			time.Sleep(time.Duration(*updateInterval) * time.Second)
		}

		input := &s3.GetObjectInput{
			Bucket: mintBucket,
			Key:    &mintKey,
		}

		output, err := client.GetObject(input)
		if err != nil {
			log.Printf("Could not fetch credentials file: %v", err)
			continue
		}

		credentialsContent, _ := ioutil.ReadAll(output.Body)

		credentialsData := &CredentialsData{}
		err = json.Unmarshal(credentialsContent, credentialsData)
		if err != nil {
			log.Printf("Downloaded credentials file does not contain valid json: %s", err)
			continue
		}

		err = ioutil.WriteFile(localTmpFile, credentialsContent, 0600)
		if err != nil {
			log.Printf("Could not persist credentials to disk: %s", err)
			continue
		}

		// TODO check if credentials changed; compare written files by hashing
		newCredentials := true

		if newCredentials {

			err = os.Rename(localTmpFile, localFile)
			if err != nil {
				log.Printf("Could not activate new credentials: %s", err)
				continue
			}

			log.Printf("Got new credentials: application_username=%s, client_id=%s")
		}
	}
}
