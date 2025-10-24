import React, { useState } from "react";
import {
  Button,
  Form,
  FormControl,
  FormField,
  FormLabel,
  FormMessage,
  Input,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  ModalTitle,
  Select,
  Spinner,
  TabList,
  TabTrigger,
  TabPanel,
  TabPanels,
  Tabs,
  Table,
  TableBody,
  TableCell,
  TableContent,
  TableElement,
  TableHead,
  TableHeader,
  TableRow,
  Textarea,
  ToastProvider,
  useToast,
} from "./index.js";

export default {
  title: "UI/Primitives",
  parameters: {
    layout: "padded",
  },
};

export const FormControls = {
  name: "Champs de formulaire",
  render: () => (
    <Form className="w-full max-w-lg">
      <FormField>
        <FormLabel htmlFor="storybook-email">Adresse e-mail</FormLabel>
        <FormControl>
          <Input id="storybook-email" placeholder="nom@domaine.com" />
        </FormControl>
        <FormMessage variant="default">L'adresse doit être valide.</FormMessage>
      </FormField>
      <FormField>
        <FormLabel htmlFor="storybook-comment">Commentaire</FormLabel>
        <FormControl>
          <Textarea id="storybook-comment" placeholder="Décrivez votre besoin" rows={4} />
        </FormControl>
      </FormField>
      <FormField>
        <FormLabel htmlFor="storybook-select">Tri</FormLabel>
        <FormControl>
          <Select id="storybook-select" defaultValue="latest">
            <option value="latest">Plus récent</option>
            <option value="alpha">Alphabétique</option>
          </Select>
        </FormControl>
      </FormField>
    </Form>
  ),
};

export const ModalExample = {
  name: "Modale",
  render: () => {
    function Example() {
      const [open, setOpen] = useState(false);
      return (
        <div className="space-y-4">
          <Button variant="primary" onClick={() => setOpen(true)}>
            Ouvrir la modale
          </Button>
          <Modal open={open} onClose={() => setOpen(false)} labelledBy="storybook-modal-title">
            <ModalHeader>
              <ModalTitle id="storybook-modal-title">Confirmation</ModalTitle>
            </ModalHeader>
            <ModalBody>
              <p className="text-sm text-slate-300">Cette modale illustre la présentation par défaut.</p>
            </ModalBody>
            <ModalFooter>
              <Button variant="ghost" data-modal-dismiss>
                Fermer
              </Button>
              <Button variant="primary" onClick={() => setOpen(false)}>
                Confirmer
              </Button>
            </ModalFooter>
          </Modal>
        </div>
      );
    }

    return <Example />;
  },
};

export const TabsExample = {
  name: "Onglets",
  render: () => (
    <Tabs defaultValue="overview">
      <TabList>
        <TabTrigger value="overview">Vue d'ensemble</TabTrigger>
        <TabTrigger value="details">Détails</TabTrigger>
      </TabList>
      <TabPanels>
        <TabPanel value="overview">
          <p>Affichez ici une synthèse des informations principales.</p>
        </TabPanel>
        <TabPanel value="details">
          <p>Détaillez le contenu complémentaire dans ce panneau.</p>
        </TabPanel>
      </TabPanels>
    </Tabs>
  ),
};

function ToastStory() {
  const { show } = useToast();
  return (
    <div className="flex flex-col gap-3">
      <Button
        variant="primary"
        onClick={() =>
          show({
            title: "Notification",
            description: "Toast déclenché depuis Storybook.",
            variant: "info",
            actionLabel: "Compris",
          })
        }
      >
        Lancer un toast
      </Button>
    </div>
  );
}

export const ToastNotifications = {
  name: "Toasts",
  render: () => (
    <ToastProvider>
      <ToastStory />
    </ToastProvider>
  ),
};

export const TableExample = {
  name: "Tableau",
  render: () => (
    <Table className="w-full max-w-3xl">
      <TableContent>
        <TableElement>
          <TableHeader>
            <TableRow>
              <TableHead>Stratégie</TableHead>
              <TableHead>Performance</TableHead>
              <TableHead>Risque</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableRow>
              <TableCell>Momentum AI</TableCell>
              <TableCell>+14,2 %</TableCell>
              <TableCell>Modéré</TableCell>
            </TableRow>
            <TableRow>
              <TableCell>Scalper X</TableCell>
              <TableCell>+7,8 %</TableCell>
              <TableCell>Élevé</TableCell>
            </TableRow>
          </TableBody>
        </TableElement>
      </TableContent>
    </Table>
  ),
};

export const SpinnerExample = {
  name: "Spinner",
  render: () => (
    <div className="flex items-center gap-4">
      <Spinner size="sm" />
      <Spinner size="md" />
      <Spinner size="lg" />
    </div>
  ),
};
